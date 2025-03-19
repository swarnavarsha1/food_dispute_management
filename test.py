import json
import os
from dotenv import load_dotenv
import api2
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

# Image file extensions
image_extensions = ['.jpg', '.jpeg']

# API URL
url = "http://localhost:8000/"

# Create output directory if it doesn't exist
output_dir = "gemini_results"
os.makedirs(output_dir, exist_ok=True)

# Create a timestamp for unique filename
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_file = f"{output_dir}/detected_objects_{timestamp}.json"
output_file_2 = f"{output_dir}/detected_objects_text_{timestamp}.txt"

# Process each image and collect results
all_results = []
all_results_2 = []
responses = api2.iterate_images_from_url(url)

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
                prompt = """Extract ALL text and information from this bill/receipt with extreme attention to detail.
                
                First, transcribe EVERY line of text visible on the receipt exactly as it appears.
                
                Then, format the result as clean JSON without markdown formatting. Include:
                - store_name: The name of the restaurant or store
                - date: The date and time if available
                - order_info: Any order numbers, delivery info, or service type
                - server: Server or staff name if present
                - customer_info: Number of guests, customer name, etc.
                - items: An array of ALL items on the receipt, including:
                  * name: Full item name EXACTLY as shown (even simple items like "RICE")
                  * quantity: Item quantity if specified (if not specified, omit this field)
                  * price: Price if available (if not specified, omit this field)
                  * specifications: Any special instructions, spice levels, etc.
                
                Make sure to capture EVERY item mentioned on the receipt, even if it's just a single word like "RICE" or lacks quantity/price information.
                
                Include these additional fields if present:
                - subtotal: Subtotal if available
                - tax: Tax if available
                - total: Total amount if available
                - additional_info: Any other relevant information not captured elsewhere
                
                Do not omit any items - completeness is critical. If you're unsure about what an item is, include it anyway."""
            else:
                prompt = "Identify and describe this food dish in detail. What cuisine is it? What are the main ingredients visible? Is this a well-known dish, and if so, what is it called?"
            
            # Send the image to Gemini for analysis
            gemini_response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[image, prompt]
            )
            
            # Print detected description
            out = f"\nAnalysis of Image {i + 1}:"
            all_results_2.append(out)
            print(out)
            
            description = gemini_response.text
            
            # For bills, perform a verification step to ensure all items are captured
            if is_bill:
                # Extract raw text from the image as a separate step to cross-check
                verification_prompt = "Transcribe ALL text visible in this receipt/bill exactly as it appears, line by line. Include every line, even if it's just a single word or seems unimportant."
                verification_response = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=[image, verification_prompt]
                )
                raw_text = verification_response.text
                print("\nRaw text verification:\n", raw_text)
            
            # Format the description for display
            if is_bill:
                try:
                    # Clean up the JSON if it contains markdown formatting or extra characters
                    if description.startswith("```json"):
                        description = description.replace("```json", "").replace("```", "").strip()
                    
                    # Try to parse as JSON
                    json_data = json.loads(description)
                    
                    # Save the clean JSON to a separate file
                    bill_json_file = f"{output_dir}/bill_{i+1}_{timestamp}.json"
                    with open(bill_json_file, 'w') as bill_file:
                        json.dump(json_data, bill_file, indent=2)
                    print(f"Bill JSON saved to {bill_json_file}")
                    
                    # Format for display
                    formatted_output = json.dumps(json_data, indent=2)
                    print(formatted_output)
                except json.JSONDecodeError as e:
                    print(f"Warning: Could not parse bill as JSON: {e}")
                    # Try once more with a follow-up prompt to fix the JSON
                    try:
                        print("Attempting to fix JSON and ensure all items are included...")
                        fix_json_prompt = f"""The following extraction from a receipt may be missing items or have syntax errors:

{description}

Create valid JSON with these requirements:
1. Include EVERY item mentioned on the receipt (like "RICE" which might have been missed)
2. Fix any JSON syntax errors
3. Return ONLY valid JSON with no markdown formatting

The JSON should capture every single line item on the receipt, even simple entries or those without quantities."""
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
                        print(f"Fixed bill JSON saved to {bill_json_file}")
                        formatted_output = json.dumps(json_data, indent=2)
                    except Exception:
                        # Last resort: format as bullet points
                        bullet_points = description.split("\n")
                        formatted_output = "\n".join([f"• {point.strip()}" for point in bullet_points if point.strip()])
                    print(formatted_output)
            else:
                # Format food descriptions as bullet points
                bullet_points = description.split(". ")
                formatted_output = "\n".join([f"• {point.strip()}" for point in bullet_points if point.strip()])
                print(formatted_output)
            
            all_results_2.append(formatted_output)
            
            # Store result with image identifier
            result = {
                "image_id": i + 1,
                "type": "bill" if is_bill else "food",
                "timestamp": datetime.now().isoformat(),
                "description": description
            }
            all_results.append(result)
            
        except Exception as e:
            print(f"Error processing image {i + 1}: {str(e)}")
            result = {
                "image_id": i + 1,
                "error": str(e)
            }
            all_results.append(result)
            all_results_2.append(f"• Error processing image {i + 1}: {str(e)}")
    else:
        print(f"Failed to fetch image {i + 1} from API. Status code: {response.status_code}")
        result = {
            "image_id": i + 1,
            "error": f"HTTP Error: {response.status_code}"
        }
        all_results.append(result)
        all_results_2.append(f"• Failed to fetch image {i + 1} from API. Status code: {response.status_code}")

# Write results to file
with open(output_file, 'w') as f:
    json.dump(all_results, f, indent=4)
with open(output_file_2, 'w', encoding='utf-8') as f:
    f.write("\n".join(all_results_2))

print(f"\nResults have been written to {output_file}")