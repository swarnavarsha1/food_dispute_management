import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import os
from io import BytesIO
from PIL import Image

def iterate_images_from_url(url):
    # List to store image URLs
    image_urls = []
    
    # Valid image extensions
    image_extensions = ['.jpg', '.jpeg']
    
    try:
        # Send a GET request to the URL
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        # Parse the HTML content
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find all img tags
        img_tags = soup.find_all('img')
        
        # Find all anchor tags that might link to images
        a_tags = soup.find_all('a')
        
        # Process img tags
        for img in img_tags:
            src = img.get('src')
            if src:
                # Make the URL absolute
                img_url = urljoin(url, src)
                
                # Check if the URL points to an image
                parsed_url = urlparse(img_url)
                if any(os.path.splitext(parsed_url.path)[1].lower() == ext for ext in image_extensions):
                    image=requests.get(img_url)
                    image_urls.append(image)
                    
                    # print(f"Found image: {img_url}")
                    
                    # Example: download and verify the image
                    try:
                        img_response = requests.get(img_url)
                        img_data = BytesIO(img_response.content)
                        img = Image.open(img_data)
                        print(f"  Size: {img.size}, Format: {img.format}")
                    except Exception as e:
                        print(f"  Error opening image: {e}")
        
        # Process anchor tags that might link to images
        for a in a_tags:
            href = a.get('href')
            if href:
                # Make the URL absolute
                link_url = urljoin(url, href)
                
                # Check if the URL points to an image
                parsed_url = urlparse(link_url)
                
                if any(os.path.splitext(parsed_url.path)[1].lower() == ext for ext in image_extensions):
                    if link_url not in image_urls:  # Avoid duplicates
                        image=requests.get(link_url)
                        image_urls.append(image)
                        # print(f"Found image link: {link_url}")
                        
                        # Example: download and verify the image
                        try:
                            img_response = requests.get(link_url)
                            img_data = BytesIO(img_response.content)
                            img = Image.open(img_data)
                            print(f"  Size: {img.size}, Format: {img.format}")
                        except Exception as e:
                            print(f"  Error opening image: {e}")
        
    except Exception as e:
        print(f"Error fetching URL: {e}")
    
    return image_urls

# Example usage
if __name__ == "__main__":
    url = "http://localhost:8000/"  # Replace with your HTTP URL
    images = iterate_images_from_url(url)
    print(f"Total images found: {len(images)}")
    print(images)