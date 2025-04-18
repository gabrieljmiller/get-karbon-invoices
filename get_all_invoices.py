import http.client
import json
import csv
import urllib
import os
import sys
from dotenv import load_dotenv
from datetime import datetime


# get base path depending on whether script is run from source or executable
try:
    base_path = os.path.dirname(sys.executable)
except Exception:
    base_path = os.path.dirname(os.path.abspath(__file__))

# Path to the .env file in the same directory as the executable/script
env_path = os.path.join(base_path, '.env')
print(f'env path: {env_path}')

# Load environment variables from the .env file
load_dotenv(dotenv_path=env_path)

conn = http.client.HTTPSConnection("api.karbonhq.com")
payload = ''
headers = {
    'Accept': 'application/json',
    'Authorization': os.getenv("bearer_token"),
    'AccessKey': os.getenv("access_key")
}

# Get current date
current_date = datetime.now().date()

def list_all_inv():
    # gets all invoices in Karbon and gets address from contact instead of invoice. takes a while and spreadsheet needs filtered down to what you need

    # Set up the connection and request
    
    # Prepare the CSV file to write
    print("Retrieving invoice list...")
    with open('invoices.csv', mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)

        # Write header row
        writer.writerow(['Client', 'Invoice Number','Invoice Total','Street','City','State','Zip','Status','Due Date','Invoice Date','Invoice Key','Email Address'])

        skip_value = 0  # Start from the first page of invoices
        seen_invoice_keys = set()  # To track already processed invoice keys
        
        while True:
            # Make the request with the current $skip value
            conn.request(f"GET", f"/v3/Invoices?$orderby=InvoiceDate&$top=100&$skip={skip_value}", payload, headers)
            res = conn.getresponse()
            data = res.read()

            # Decode JSON response
            inv_list_json_data = json.loads(data)

            # Extract the invoices data from the JSON response
            invoices = inv_list_json_data.get('value', [])

            # If there are no invoices returned, break the loop
            if not invoices:
                break

            for invoice in invoices:

                # Check if invoice already processed based on its InvoiceKey
                invoice_key = invoice.get('InvoiceKey', '')
                if invoice_key in seen_invoice_keys:
                    continue  # Skip if we've already seen this invoice
                
                # Mark this invoice as processed
                seen_invoice_keys.add(invoice_key)

                # get client key
                client = invoice.get('Client', {})
                client_key = client.get('ClientKey','')

                # get client data
                conn.request("GET", f"/v3/Organizations/{client_key}?$expand=BusinessCards", payload, headers)
                res2 = conn.getresponse()
                data2 = res2.read()
                inv_detail_json_data = json.loads(data2)

                # get address fields from client data
                business_card_list = inv_detail_json_data.get('BusinessCards',{})
                if business_card_list:
                    address_list = business_card_list[0].get('Addresses',{})
                    address_lines = address_list[0].get('AddressLines','')
                    city = address_list[0].get('City','')
                    state = address_list[0].get('StateProvinceCounty','')
                    zipcode = address_list[0].get('ZipCode','')
                else:
                    address_lines = ''
                    city = ''
                    state = ''
                    zipcode = ''

                # consolidate address into a 2-line string
                full_address = f"{address_lines}\n{city} {state}, {zipcode}"

                # declare vars for csv rows
                invoice_number = invoice.get('InvoiceNumber', '')
                client_name = client.get('Name', '')
                total = invoice.get('InvoiceTotal', '')
                status = invoice.get('InvoiceStatus', '')
                due_date_raw = invoice.get('PaymentDueDate', '')
                due_date_formatted = due_date_raw.split("T")[0]
                invoice_date_raw = invoice.get('InvoiceDate', '')
                invoice_date_formatted = invoice_date_raw.split("T")[0]
                email = client.get('EmailAddress', '')

                # Write each line item of an invoice as a separate row
                writer.writerow([client_name, invoice_number, total, address_lines, city, state, zipcode, status, due_date_formatted, invoice_date_formatted, invoice_key, email])
                print(f'{invoice_number}, {client_name}')

            # Increase the skip value for the next batch of invoices
            skip_value += 100

    print("CSV file 'invoices.csv' has been created.")

def get_inv_line_items():
    # get invoice with line items from invoice key from spreadsheet generated by list_all_inv function
    print("Retrieving line items....")
    with open('invoices.csv', mode='r', encoding='utf-8-sig') as inv_no_file:
        
        # create csv reader and skip header row
        csv_reader = csv.reader(inv_no_file)
        next(csv_reader)

        # create csv file to write
        with open(f'{current_date} invoices_line_items.csv', mode='w', newline='', encoding='utf-8') as new_file:
            csv_writer = csv.writer(new_file, quoting=csv.QUOTE_NONNUMERIC)

            # prepare header row
            csv_writer.writerow(['Invoice Number', 'Client', 'Street', 'City', 'State', 'Zipcode', 'Email', 'Invoice Total', 'Status', 'Due Date', 'Invoice Date', 'Line Item Description', 'Line Item Total', 'Work Title','Work Type', 'Work URL'])

            # start reading csv and getting invoice with key
            for row in csv_reader:
                inv_key = str(row[10]).strip()
                inv_key_encoded = urllib.parse.quote(inv_key)
                conn.request('GET', f'/v3/Invoices/{inv_key_encoded}?$expand=LineItems', payload, headers)
                res = conn.getresponse()
                data = res.read()

                # Decode JSON response
                json_data = json.loads(data.decode("utf-8"))

                # get invoice info
                inv_no = row[1]
                client_name = row[0]
                street = row[3]
                city = row[4]
                state = row[5]
                zipcode = row[6]
                inv_total = row[2]
                status = row[7]
                due_date = row[8]
                inv_date = row[9]
                email = row[10]

                # Get line items (work items)
                line_items = json_data.get('LineItems', [])
                
                for item in line_items:
                    billable_item_type = item.get('BillableItemType', '')
                    description = item.get('Description', '')
                    line_item_total = item.get('Amount', 0)
                    if billable_item_type == 'Entity' or billable_item_type == 'TimeEntry':
                        work_key = item.get('BillableItemEntityKey', '')
                        work_url = f'https://app2.karbonhq.com/YtfB1S5FYHG#/work/{work_key}/tasks'

                        # get work item
                        conn.request('GET', f'/v3/WorkItems/{work_key}', payload, headers)
                        res = conn.getresponse()
                        data = res.read()
                        work_json = json.loads(data.decode("utf-8"))
                        # print(work_json)

                        # get work info
                        work_title = work_json.get('Title', '')
                        work_type = work_json.get('WorkType', '')
                        # work_template = work_json.get('WorkTemplateTile', '') not working - typo is in documentation, returning as empty, probably Karbon issue
                    else:
                        work_url = ''
                        work_title = ''
                        work_type = ''
                    
                    # Write a new row for each line item with the original invoice details
                    csv_writer.writerow([inv_no, client_name, street, city, state, zipcode, email, inv_total, status, due_date, inv_date, description, line_item_total, work_title, work_type, work_url])

                print(f"Processed invoice {inv_no} with {len(line_items)} line items.")
    
    print("Spreadsheet with line items created.")

def get_additional_payment_info(payment_key):
    conn.request('GET', f'/v3/Payments/{payment_key}', payload, headers)
    res = conn.getresponse()
    data = res.read()
    payment_json = json.loads(data.decode("utf-8"))
    payment_method = payment_json.get('PaymentMethod', '')
    return payment_method

def get_inv_payments():
    # get payments for invoices
    print("Retrieving payments....")
    with open('invoices.csv', mode='r', encoding='utf-8-sig') as inv_no_file:
        
        # create csv reader and skip header row
        csv_reader = csv.reader(inv_no_file)
        next(csv_reader)

        # create csv file to write
        with open(f'{current_date} invoices_payments.csv', mode='w', newline='', encoding='utf-8') as new_file:
            csv_writer = csv.writer(new_file, quoting=csv.QUOTE_NONNUMERIC)

            # prepare header row
            csv_writer.writerow(['Invoice Number', 'Client', 'Street', 'City', 'State', 'Zipcode', 'Email', 'Invoice Total', 'Status', 'Due Date', 'Invoice Date', 'Payment Date', 'Payment Amount', 'Payment Type', 'Payment Key', 'Payment Method'])

            # start reading csv and getting invoice with key
            for row in csv_reader:
                inv_key = str(row[10]).strip()
                inv_key_encoded = urllib.parse.quote(inv_key)
                conn.request('GET', f'/v3/Invoices/{inv_key_encoded}?$expand=Payments', payload, headers)
                res = conn.getresponse()
                data = res.read()
            
                # Decode JSON response
                json_data = json.loads(data.decode("utf-8"))

                # get invoice info
                inv_no = row[1]
                client_name = row[0]
                street = row[3]
                city = row[4]
                state = row[5]
                zipcode = row[6]
                inv_total = row[2]
                status = row[7]
                due_date = row[8]
                inv_date = row[9]
                email = row[10]

                # Get payments
                payments = json_data.get('Payments', [])

                for payment in payments:
                    payment_date = payment.get('PaymentDate', '')
                    payment_amount = payment.get('Amount', '')
                    payment_type = payment.get('PaymentType', '')
                    payment_key = payment.get('PaymentKey', '')
                    payment_method = get_additional_payment_info(payment_key)

                    # Write a new row for each payment with the original invoice details
                    csv_writer.writerow([inv_no, client_name, street, city, state, zipcode, email, inv_total, status, due_date, inv_date, payment_date, payment_amount, payment_type, payment_key,payment_method])

                print(f"Processed invoice {inv_no} with {len(payments)} payments.")
            
    print("Spreadsheet with payments created.")

def filter_overdue():
    with open('invoices.csv',mode='r',encoding='utf-8') as inv_file:
        reader = csv.DictReader(inv_file)

    #prep headers for output csv
    headers = [field for field in reader.fieldnames if field not in ['Invoice Key', 'Status']]

    #open output csv
    with open(f'{current_date} overdue_invoices.csv', mode='w', newline='', encoding='utf-8') as overdue_file:
        writer = csv.DictWriter(overdue_file, fieldnames=headers)
        writer.writeheader()

        for row in reader:
            # skip rows that don't contain 'Awaiting Payment' in status column
            if(row['Status'] != 'AwaitingPayment'):
                continue

            # check date
            try:
                due_date = datetime.strptime(row['Due Date'], '%Y-%m-%d').date()
                if(due_date >= current_date):
                    continue
            except ValueError:
                # skip row if date format is incorrect
                continue
            
            # remove unncecessary columns
            del row['Invoice Key']
            del row['Status']

            # write row to output csv
            writer.writerow(row)
    print("Overdue invoices filtered and saved to 'overdue_invoices.csv'.")

# run functions 
get_inv_input = input("Generate new base invoice list? (y/n):")
get_line_items_input = input("Get line items? It will take much longer. (y/n):")
filter_overdue_input = input("Create a csv with only overdue invoices? (y/n):")
get_payments_input = input("Get payments for invoices? (y/n):")

if get_inv_input == "y":
    list_all_inv()
if get_line_items_input == "y":
    get_inv_line_items()

if filter_overdue_input == "y":
    filter_overdue()
if get_payments_input == "y":
    get_inv_payments()