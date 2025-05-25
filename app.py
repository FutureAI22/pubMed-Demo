import streamlit as st
import requests
import xml.etree.ElementTree as ET
import re
import pandas as pd
from time import sleep
import io
import os

# Page configuration
st.set_page_config(
    page_title="PubMed Author Email Extractor",
    page_icon="📧",
    layout="wide"
)

# Title and description
st.title("📧 PubMed Author Email Extractor")
st.markdown("Extract author contact information from PubMed publications")

# Sidebar for configuration
with st.sidebar:
    st.header("🔧 Configuration")
    
    # Try multiple methods to get API key
    api_key = None
    
    # Method 1: Streamlit secrets
    try:
        api_key = st.secrets["PUBMED_API_KEY"]
        st.success("✅ API Key loaded from Streamlit secrets")
    except:
        pass
    
    # Method 2: Environment variable
    if not api_key:
        api_key = os.getenv("PUBMED_API_KEY")
        if api_key:
            st.success("✅ API Key loaded from environment variable")
    
    # Method 3: Manual input (fallback)
    if not api_key:
        api_key = st.text_input("PubMed API Key", type="password", help="Enter your PubMed API key")
        if api_key:
            st.info("🔑 Using manually entered API key")
    
    max_results = st.slider("Maximum Results", min_value=10, max_value=10000, value=1000, step=10)
    
    st.header("📋 Filter Options")
    only_with_emails = st.checkbox("Only authors with emails", value=True)
    only_known_authors = st.checkbox("Only known authors (no 'Unknown Author')", value=True)
    enable_keyword_filter = st.checkbox("Enable keyword filtering", value=True)

# Main search interface
st.header("🔍 Search Parameters")

col1, col2 = st.columns(2)

with col1:
    search_term = st.text_input("Search Term", value="Food Addiction", help="Main search term for PubMed")
    author_filter = st.text_input("Author Name Filter (optional)", help="Filter results by specific author name")

with col2:
    title_filter = st.text_input("Title Keywords (optional)", help="Filter by keywords in title")
    email_domain_filter = st.text_input("Email Domain Filter (optional)", help="Filter by email domain (e.g., harvard.edu)")

# Advanced keyword filtering
if enable_keyword_filter:
    st.header("🎯 Keyword Filtering")
    
    default_keywords = [
        'food addiction', 'food addictive', 'addictive eating', 'eating addiction',
        'compulsive eating', 'food craving', 'hedonic eating', 'binge eating',
        'overeating', 'food reward', 'eating behavior', 'obesogenic',
        'hyperpalatable', 'food dependence', 'eating disorder'
    ]
    
    keywords_text = st.text_area(
        "Filtering Keywords (one per line)", 
        value='\n'.join(default_keywords),
        help="Articles must contain at least one of these keywords to be included"
    )
    
    keywords_list = [k.strip() for k in keywords_text.split('\n') if k.strip()]

# Helper functions
@st.cache_data
def search_pubmed(term, max_results, api_key):
    """Search PubMed and return list of PMIDs"""
    if not api_key:
        st.error("Please provide a PubMed API key")
        return []
    
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    search_url = f"{base_url}esearch.fcgi"
    
    params = {
        'db': 'pubmed',
        'term': term,
        'retmax': max_results,
        'api_key': api_key
    }
    
    try:
        response = requests.get(search_url, params=params)
        root = ET.fromstring(response.content)
        pmids = [id_elem.text for id_elem in root.findall('.//Id')]
        return pmids
    except Exception as e:
        st.error(f"Error searching PubMed: {e}")
        return []

def is_keyword_related(title, abstract, keywords_list):
    """Check if title/abstract contains any of the specified keywords"""
    if not keywords_list:
        return True
    
    text_to_check = f"{title} {abstract}".lower()
    return any(keyword.lower() in text_to_check for keyword in keywords_list)

def fetch_article_details(pmids, api_key, filters):
    """Fetch detailed article information and extract data based on filters"""
    if not pmids:
        return []
    
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    fetch_url = f"{base_url}efetch.fcgi"
    results = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # Process in batches of 20
    total_batches = len(pmids) // 20 + (1 if len(pmids) % 20 else 0)
    
    for i in range(0, len(pmids), 20):
        batch = pmids[i:i+20]
        batch_num = i // 20 + 1
        
        status_text.text(f"Processing batch {batch_num}/{total_batches}...")
        progress_bar.progress(batch_num / total_batches)
        
        params = {
            'db': 'pubmed',
            'id': ','.join(batch),
            'rettype': 'xml',
            'api_key': api_key
        }
        
        try:
            response = requests.get(fetch_url, params=params)
            root = ET.fromstring(response.content)
            
            # Process each article
            for article in root.findall('.//PubmedArticle'):
                # Extract title
                title_elem = article.find('.//ArticleTitle')
                title = title_elem.text if title_elem is not None and title_elem.text else "No title"
                
                # Extract abstract
                abstract_elem = article.find('.//AbstractText')
                abstract = abstract_elem.text if abstract_elem is not None and abstract_elem.text else ""
                
                # Apply keyword filtering
                if filters['enable_keyword_filter'] and not is_keyword_related(title, abstract, filters['keywords_list']):
                    continue
                
                # Apply title filter
                if filters['title_filter'] and filters['title_filter'].lower() not in title.lower():
                    continue
                
                # Extract authors and emails
                authors = article.findall('.//Author')
                
                # Collect all emails from affiliations
                article_emails = set()
                affiliations = article.findall('.//Affiliation')
                for aff in affiliations:
                    if aff.text:
                        email_matches = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', aff.text)
                        article_emails.update(email_matches)
                
                # Process each author
                for author in authors:
                    # Get author name
                    last_name = author.find('.//LastName')
                    first_name = author.find('.//ForeName')
                    
                    # Skip unknown authors if filter is enabled
                    if filters['only_known_authors']:
                        if last_name is None or not last_name.text or not last_name.text.strip():
                            continue
                    
                    author_name = "Unknown Author"
                    if last_name is not None and last_name.text:
                        author_name = last_name.text.strip()
                        if first_name is not None and first_name.text and first_name.text.strip():
                            author_name = f"{first_name.text.strip()} {last_name.text.strip()}"
                    
                    # Apply author filter
                    if filters['author_filter'] and filters['author_filter'].lower() not in author_name.lower():
                        continue
                    
                    # Get author emails
                    author_emails = set()
                    author_aff = author.find('.//Affiliation')
                    if author_aff is not None and author_aff.text:
                        email_matches = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', author_aff.text)
                        author_emails.update(email_matches)
                    
                    # Use article emails if no author-specific email
                    if not author_emails and article_emails:
                        author_emails = article_emails
                    
                    # Apply email filters
                    if filters['only_with_emails'] and not author_emails:
                        continue
                    
                    # Add entries
                    if author_emails:
                        for email in author_emails:
                            # Apply email domain filter
                            if filters['email_domain_filter'] and filters['email_domain_filter'].lower() not in email.lower():
                                continue
                            
                            results.append({
                                'title': title,
                                'author': author_name,
                                'email': email
                            })
                    elif not filters['only_with_emails']:
                        results.append({
                            'title': title,
                            'author': author_name,
                            'email': 'No email found'
                        })
            
            sleep(0.1)  # Be respectful to API
            
        except Exception as e:
            st.warning(f"Error processing batch {batch_num}: {e}")
            continue
    
    progress_bar.empty()
    status_text.empty()
    
    return results

def remove_duplicates(data):
    """Remove duplicate entries"""
    seen = set()
    unique_data = []
    
    for row in data:
        title = (row['title'] or '').strip().lower()
        author = (row['author'] or '').strip().lower()
        email = (row['email'] or '').strip().lower()
        
        key = (title, author, email)
        
        if key not in seen:
            seen.add(key)
            unique_data.append(row)
    
    return unique_data

# Search button and execution
if st.button("🚀 Start Search", type="primary"):
    if not api_key:
        st.error("Please provide a PubMed API key in the sidebar")
    elif not search_term:
        st.error("Please enter a search term")
    else:
        # Prepare filters
        filters = {
            'only_with_emails': only_with_emails,
            'only_known_authors': only_known_authors,
            'enable_keyword_filter': enable_keyword_filter,
            'keywords_list': keywords_list if enable_keyword_filter else [],
            'author_filter': author_filter,
            'title_filter': title_filter,
            'email_domain_filter': email_domain_filter
        }
        
        with st.spinner("Searching PubMed..."):
            # Step 1: Search
            pmids = search_pubmed(search_term, max_results, api_key)
            
            if pmids:
                st.success(f"Found {len(pmids)} articles")
                
                # Step 2: Extract details
                with st.spinner("Extracting article details..."):
                    results = fetch_article_details(pmids, api_key, filters)
                
                if results:
                    # Step 3: Remove duplicates
                    unique_results = remove_duplicates(results)
                    
                    # Create DataFrame
                    df = pd.DataFrame(unique_results)
                    
                    # Display results
                    st.header("📊 Results")
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Total Entries", len(unique_results))
                    with col2:
                        st.metric("Duplicates Removed", len(results) - len(unique_results))
                    with col3:
                        if only_with_emails:
                            st.metric("Authors with Emails", len(unique_results))
                        else:
                            emails_count = len([r for r in unique_results if r['email'] != 'No email found'])
                            st.metric("Authors with Emails", emails_count)
                    
                    # Display data
                    st.dataframe(df, use_container_width=True)
                    
                    # Download button
                    csv_buffer = io.StringIO()
                    df.to_csv(csv_buffer, index=False)
                    csv_data = csv_buffer.getvalue()
                    
                    st.download_button(
                        label="📥 Download CSV",
                        data=csv_data,
                        file_name=f"{search_term.replace(' ', '_')}_authors.csv",
                        mime="text/csv"
                    )
                    
                else:
                    st.warning("No results found matching your criteria. Try adjusting your filters.")
            else:
                st.error("No articles found for your search term.")

# Footer
st.markdown("---")
st.markdown("💡 **Tip**: Start with broader filters and gradually narrow down your search for better results.")
