import json

def identify_missing_items(ordered_file, delivered_file):
    # Load the JSON files
    with open(ordered_file, 'r') as file1:
        ordered_orders = json.load(file1)
    
    with open(delivered_file, 'r') as file2:
        delivered_orders = json.load(file2)
    
    # Create dictionaries keyed by order_id for easier lookup
    ordered_dict = {order["order_id"]: order for order in ordered_orders}
    delivered_dict = {order["order_id"]: order for order in delivered_orders}
    
    # Track all discrepancies
    missing_items_report = []
    other_discrepancies = []
    
    # Find orders that are in ordered but not delivered at all
    completely_missing_orders = set(ordered_dict.keys()) - set(delivered_dict.keys())
    if completely_missing_orders:
        for order_id in completely_missing_orders:
            missing_items_report.append(f"ENTIRE ORDER #{order_id} MISSING - Customer: {ordered_dict[order_id]['customer_name']}")
            for item in ordered_dict[order_id]['items']:
                missing_items_report.append(f"  - {item['quantity']} x {item['name']}")
    
    # For orders that are in both files, check for missing items
    common_order_ids = set(ordered_dict.keys()) & set(delivered_dict.keys())
    
    for order_id in common_order_ids:
        ordered_items = ordered_dict[order_id]["items"]
        delivered_items = delivered_dict[order_id]["items"]
        
        # Create dictionaries of items with quantities for easier comparison
        ordered_items_dict = {}
        for item in ordered_items:
            item_name = item["name"]
            if item_name in ordered_items_dict:
                ordered_items_dict[item_name]["quantity"] += item["quantity"]
            else:
                ordered_items_dict[item_name] = item.copy()
        
        delivered_items_dict = {}
        for item in delivered_items:
            item_name = item["name"]
            if item_name in delivered_items_dict:
                delivered_items_dict[item_name]["quantity"] += item["quantity"]
            else:
                delivered_items_dict[item_name] = item.copy()
        
        # Find missing or fewer quantity items
        has_missing_items = False
        order_missing_items = []
        
        for item_name, item_details in ordered_items_dict.items():
            if item_name not in delivered_items_dict:
                has_missing_items = True
                order_missing_items.append(f"  - MISSING: {item_details['quantity']} x {item_name}")
            elif delivered_items_dict[item_name]["quantity"] < item_details["quantity"]:
                has_missing_items = True
                missing_qty = item_details["quantity"] - delivered_items_dict[item_name]["quantity"]
                order_missing_items.append(f"  - SHORT: {missing_qty} x {item_name} (ordered {item_details['quantity']}, delivered {delivered_items_dict[item_name]['quantity']})")
        
        # Check for extra items (delivered but not ordered or more quantity)
        extra_items = []
        for item_name, item_details in delivered_items_dict.items():
            if item_name not in ordered_items_dict:
                extra_items.append(f"  - EXTRA: {item_details['quantity']} x {item_name} (not ordered)")
            elif delivered_items_dict[item_name]["quantity"] > ordered_items_dict[item_name]["quantity"]:
                extra_qty = item_details["quantity"] - ordered_items_dict[item_name]["quantity"]
                extra_items.append(f"  - EXTRA: {extra_qty} x {item_name} (ordered {ordered_items_dict[item_name]['quantity']}, delivered {item_details['quantity']})")
        
        # Add to appropriate reports
        if has_missing_items:
            missing_items_report.append(f"ORDER #{order_id} - Customer: {ordered_dict[order_id]['customer_name']} - MISSING ITEMS:")
            missing_items_report.extend(order_missing_items)
        
        if extra_items:
            other_discrepancies.append(f"ORDER #{order_id} - Customer: {ordered_dict[order_id]['customer_name']} - EXTRA ITEMS:")
            other_discrepancies.extend(extra_items)
    
    # Find orders that were delivered but not in the ordered file
    extra_orders = set(delivered_dict.keys()) - set(ordered_dict.keys())
    if extra_orders:
        for order_id in extra_orders:
            other_discrepancies.append(f"UNEXPECTED ORDER #{order_id} - Delivered to: {delivered_dict[order_id]['customer_name']}")
            for item in delivered_dict[order_id]['items']:
                other_discrepancies.append(f"  - {item['quantity']} x {item['name']}")
    
    # Print the results
    print("=== DELIVERY DISCREPANCY REPORT ===\n")
    
    print("MISSING ITEMS (HIGH PRIORITY):")
    if missing_items_report:
        for line in missing_items_report:
            print(line)
    else:
        print("  None - All items delivered correctly")
    
    print("\nOTHER DISCREPANCIES:")
    if other_discrepancies:
        for line in other_discrepancies:
            print(line)
    else:
        print("  None")

# Example usage
if __name__ == "__main__":
    identify_missing_items("customer_ordered.json", "restaurant_delivered.json")