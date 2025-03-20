import json
import os
from dotenv import load_dotenv
import load_images
from datetime import datetime
from PIL import Image
from io import BytesIO
import base64
from openai import OpenAI

# Load environment variables
load_dotenv()

# OpenAI API key
openai_api_key = os.environ.get("OPENAI_API_KEY")

# Initialize OpenAI Client
client = OpenAI(api_key=openai_api_key)

# API URL
url = "http://localhost:8000/"

# Create output directory if it doesn't exist
output_dir = "gpt_results"
os.makedirs(output_dir, exist_ok=True)

# Create a timestamp for unique filename
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_file = f"{output_dir}/detected_objects_{timestamp}.json"

# Function to encode image to base64
def encode_image(image):
    buffered = BytesIO()
    image.save(buffered, format="JPEG")
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

# Process each image and collect results
all_results = []
responses = load_images.iterate_images_from_url(url)

for i, response in enumerate(responses):
    # Check if the request was successful
    if response.status_code == 200:
        # Create an image object from the response content
        try:
            img_data = BytesIO(response.content)
            image = Image.open(img_data)
            
            # Encode the image
            base64_image = encode_image(image)
            
            # Determine if the image might be a food dish or a bill
            # First, let's try to determine if it's a bill or food
            type_check_completion = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Is this image primarily a document/bill/receipt or is it food/dish? Just answer with one word: 'bill' or 'food'"},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                        ]
                    }
                ]
            )
            
            image_type = type_check_completion.choices[0].message.content.strip().lower()
            
            if "bill" in image_type or "receipt" in image_type or "document" in image_type:
                is_bill = True
                # Enhanced prompt for more accurate bill extraction
                prompt = """Extract ALL text and information from this bill/receipt with extreme attention to detail.

First, carefully scan the ENTIRE receipt for ALL ITEMS, especially paying attention to single-word items like "RICE", "WATER", "SODA", etc.

Format the result as clean JSON without markdown formatting. Include:
- store_name: The name of the restaurant or store
- date: The date and time if available
- order_info: Any order numbers, delivery info, or service type
- server: Server or staff name if present
- customer_info: Number of guests, customer name, etc.
- items: An array of ALL items on the receipt, including:
  * name: Full item name EXACTLY as shown
  * quantity: Item quantity if specified (if not specified, omit this field)
  * price: Price if available (if not specified, omit this field)
  * specifications: Any special instructions, spice levels, etc.

Include these additional fields if present:
- subtotal: Subtotal if available
- tax: Tax if available
- total: Total amount if available
- additional_info: Any other relevant information not captured elsewhere

IMPORTANT: Make sure to capture EVERY single item mentioned on the receipt, even if it's just a single word like "RICE" or lacks quantity/price information."""
            else:
                is_bill = False
                prompt = "What is this food dish? Provide ONLY the dish name in 1-3 words. For example: 'Chicken Tikka Masala', 'Biryani', 'Hot Dog', etc. No descriptions, just the name."
            
            # Send the image to GPT for analysis
            gpt_completion = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                        ]
                    }
                ]
            )
            
            # Get the response content
            description = gpt_completion.choices[0].message.content
            
            # Handle bill vs food differently
            if is_bill:
                try:
                    # Clean up the JSON if it contains markdown formatting or extra characters
                    if description.startswith("```json"):
                        description = description.replace("```json", "").replace("```", "").strip()
                    
                    # Try to parse as JSON
                    json_data = json.loads(description)
                    
                    # Add verification step for bills to catch missing items
                    verification_prompt = """Please look at this receipt image one more time and list ONLY any short, single-word items or easily missed items that might be on the receipt (like "RICE", "SODA", "WATER", etc.). 
                    
Don't repeat items you've already found - only list additional items that might have been missed. If you don't see any additional items, just say "No additional items".
                    
Be especially attentive to the middle section of the receipt where shorter items might appear."""
                    
                    verification_completion = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": verification_prompt},
                                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                                ]
                            }
                        ]
                    )
                    
                    verification_result = verification_completion.choices[0].message.content.strip()
                    
                    # If additional items found, try to add them to the JSON
                    if verification_result.lower() != "no additional items" and "no additional" not in verification_result.lower():
                        # Make a list of item names already in the JSON
                        existing_items = [item["name"].upper() for item in json_data.get("items", [])]
                        
                        # Parse potential missing items from the verification
                        potential_items = [line.strip() for line in verification_result.split('\n') if line.strip()]
                        for item_text in potential_items:
                            # Extract just the item name if there's additional text
                            item_name = item_text.split(':')[0] if ':' in item_text else item_text
                            item_name = item_name.replace('-', '').replace('*', '').strip().upper()
                            
                            # If this looks like a valid item name and isn't already in our list
                            if item_name and len(item_name) > 1 and item_name not in existing_items:
                                json_data.setdefault("items", []).append({"name": item_name})
                                print(f"Added missing item from verification: {item_name}")
                    
                    # Save the clean JSON to a separate file
                    bill_json_file = f"{output_dir}/bill_{i+1}_{timestamp}.json"
                    with open(bill_json_file, 'w') as bill_file:
                        json.dump(json_data, bill_file, indent=2)
                    print(f"Image {i+1}: Bill JSON saved to {bill_json_file}")
                    
                    # Store result with image identifier
                    result = {
                        "image_id": i + 1,
                        "type": "bill",
                        "description": json_data
                    }
                except json.JSONDecodeError as e:
                    print(f"Warning: Could not parse bill as JSON: {e}")
                    # Try once more with a follow-up prompt to fix the JSON
                    try:
                        fix_json_prompt = f"""The following extraction from a receipt has syntax errors:
{description}

Fix the JSON syntax errors and return ONLY valid JSON without markdown formatting.
Make sure to include ALL items, especially single-word items like "RICE"."""

                        fix_completion = client.chat.completions.create(
                            model="gpt-4o",
                            messages=[{"role": "user", "content": fix_json_prompt}]
                        )
                        fixed_json_text = fix_completion.choices[0].message.content
                        if fixed_json_text.startswith("```json"):
                            fixed_json_text = fixed_json_text.replace("```json", "").replace("```", "").strip()
                        
                        json_data = json.loads(fixed_json_text)
                        bill_json_file = f"{output_dir}/bill_{i+1}_{timestamp}.json"
                        with open(bill_json_file, 'w') as bill_file:
                            json.dump(json_data, bill_file, indent=2)
                        print(f"Image {i+1}: Fixed bill JSON saved to {bill_json_file}")
                        
                        # Store result with image identifier
                        result = {
                            "image_id": i + 1,
                            "type": "bill",
                            "description": json_data
                        }
                    except Exception as e:
                        print(f"Error fixing JSON for image {i+1}: {str(e)}")
                        result = {
                            "image_id": i + 1,
                            "type": "bill",
                            "error": "Failed to parse JSON",
                            "raw_text": description
                        }
            else:
                # For food, just store the dish name directly
                dish_name = description.strip()
                print(f"Image {i+1}: Food identified as {dish_name}")
                
                result = {
                    "image_id": i + 1,
                    "type": "food",
                    "dish_name": dish_name
                }
            
            all_results.append(result)
            
        except Exception as e:
            print(f"Error processing image {i + 1}: {str(e)}")
            result = {
                "image_id": i + 1,
                "error": str(e)
            }
            all_results.append(result)
    else:
        print(f"Failed to fetch image {i + 1} from API. Status code: {response.status_code}")
        result = {
            "image_id": i + 1,
            "error": f"HTTP Error: {response.status_code}"
        }
        all_results.append(result)

# Write results to file
with open(output_file, 'w') as f:
    json.dump(all_results, f, indent=4)

print(f"\nResults have been written to {output_file}")