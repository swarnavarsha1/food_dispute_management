import json
import os
from dotenv import load_dotenv
import load_images
from datetime import datetime
from PIL import Image
from io import BytesIO
from google import genai

# Load environment variables
load_dotenv()

# Gemini API key
gemini_api_key = os.environ.get("GEMINI_API_KEY")

# Initialize Gemini Client
client = genai.Client(api_key=gemini_api_key)

# API URL
url = "http://localhost:8000/"

# Create output directory if it doesn't exist
output_dir = "gemini_results"
os.makedirs(output_dir, exist_ok=True)

# Create a timestamp for unique filename
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_file = f"{output_dir}/detected_objects_{timestamp}.json"

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
            
            # Determine if the image might be a food dish or a bill
            # Send appropriate prompt to Gemini
            is_bill = False  # We'll assume it's a food image first
            
            # First, let's try to determine if it's a bill or food
            type_check_response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[image, "Is this image primarily a document/bill/receipt or is it food/dish? Just answer with one word: 'bill' or 'food'"]
            )
            
            image_type = type_check_response.text.strip().lower()
            
            if "bill" in image_type or "receipt" in image_type or "document" in image_type:
                is_bill = True
                # Enhanced prompt for more accurate bill extraction
                prompt = """Extract ALL text and information from this bill/receipt with extreme attention to detail.

First, SCAN LINE BY LINE through the ENTIRE receipt and transcribe EVERY single line of text visible, including ALL items, especially short items like "RICE", "WATER", "SODA", etc.

Then, format the result as clean JSON without markdown formatting. Include:
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

IMPORTANT: Pay special attention to single-word items (like "RICE") which can be easily missed. Make sure to include EVERY item."""
            else:
                prompt = "What is this food dish? Provide ONLY the dish name in 1-3 words. For example: 'Chicken Tikka Masala', 'Biryani', 'Hot Dog', etc. No descriptions, just the name."
            
            # Send the image to Gemini for analysis
            gemini_response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[image, prompt]
            )
            
            # Get the response content
            description = gemini_response.text
            
            # Handle bill vs food differently
            if is_bill:
                try:
                    # Clean up the JSON if it contains markdown formatting or extra characters
                    if description.startswith("```json"):
                        description = description.replace("```json", "").replace("```", "").strip()
                    
                    # Try to parse as JSON
                    json_data = json.loads(description)
                    
                    # Add verification step for bills to catch missing items
                    verification_prompt = """Analyze this receipt image carefully. 
                    
Look for ANY short, single-word items like "RICE", "SODA", "WATER", etc. that might have been missed.

List ONLY these short items if you find any. If you don't see any additional items, just respond with "No additional items found"."""
                    
                    verification_response = client.models.generate_content(
                        model="gemini-2.0-flash",
                        contents=[image, verification_prompt]
                    )
                    
                    verification_result = verification_response.text.strip()
                    
                    # Extract raw text from the image as another verification method
                    raw_text_prompt = "Transcribe ONLY the food/drink item names from this receipt, line by line. For example: CHICKEN TIKKA MASALA, RICE, NAAN, etc. Focus on the item names only."
                    raw_text_response = client.models.generate_content(
                        model="gemini-2.0-flash",
                        contents=[image, raw_text_prompt]
                    )
                    
                    raw_text_result = raw_text_response.text.strip()
                    print(f"\nRaw item verification:\n{raw_text_result}")
                    
                    # Combine verification results to check for missing items
                    if ("no additional" not in verification_result.lower()) or raw_text_result:
                        # Make a list of item names already in the JSON
                        existing_items = [item["name"].upper() for item in json_data.get("items", [])]
                        
                        # Check verification result
                        potential_items_1 = [line.strip() for line in verification_result.split('\n') if line.strip() and "no additional" not in line.lower()]
                        
                        # Check raw text result
                        potential_items_2 = [line.strip() for line in raw_text_result.split('\n') if line.strip()]
                        
                        # Combine potential items
                        all_potential_items = potential_items_1 + potential_items_2
                        
                        for item_text in all_potential_items:
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
Make sure to include ALL items mentioned on the receipt, especially short, easily-missed items like "RICE"."""

                        fix_response = client.models.generate_content(
                            model="gemini-2.0-flash",
                            contents=[fix_json_prompt]
                        )
                        fixed_json_text = fix_response.text
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