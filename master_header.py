"""
Master schema for the Lorenz account.
MASTER_COLUMNS is the fixed 79-column header every supplier file must be
mapped into before merging (taken from Merge_File_Lorenz.xlsx).
SUPPLIERS is the fixed list of suppliers reporting under the Lorenz account.
"""

MASTER_COLUMNS = [
    "Distname", "Supplier_name", "direct_indirect", "in_out_territory",
    "CustAccNbr", "CustDunsID", "CustName", "Address1", "City", "State",
    "County", "Zip", "Phone", "Country", "NoOfEmployees", "WebAddress",
    "SIC", "NAICS", "LineOfBusiness", "ParentName", "AccountType", "UOM",
    "InvoiceNumber", "Qty", "UnitCost", "UnitResale", "InvoiceDate",
    "DateRecieved", "PartNumberSubmitted", "PartNumberDescription", "Branch",
    "SalesRep", "Latitude", "Longitude", "Brand", "PartNumberActual",
    "UPCCode", "rawcustname", "rawdistaddress", "rawdistcity",
    "rawdiststate", "rawdistpostalcode", "rawdistcountry", "currency",
    "contractID", "client_CustName", "Zip_4_digit", "dnb_trade_style",
    "dnb_sales_value", "google_CustName", "google_Address1", "google_State",
    "google_Zip", "google_Country", "google_Phone", "google_WebAddress",
    "Pay_Month", "Pay_Year", "Ship_Month", "Ship_Year", "Industry",
    "Commissions", "Commission_Rate", "Cust_AM", "CEM", "Sales", "In_Out",
    "Commission_split_percentage", "Distributor_part_number", "Category",
    "google_City", "Billings", "Cheque_Number", "Pay_Date",
    "meta_data_json", "SO_Number", "PO_Number", "ship_date",
    "searched_on_google",
]

SUPPLIERS = [
    "ATP", "Bravotek", "Coilcraft", "Comchip", "Conec", "CVI Lux", "DEI",
    "Epson", "Grayhill", "Heatron", "Hongfa", "Kyocera", "Leadertech",
    "LEM", "Macronix", "Nisshinbo", "Shinelink", "SiTime", "Soracom",
    "SunLed", "Tecate", "Wall", "Winchester",
]

# Sanity check kept for developers running this file directly.
if __name__ == "__main__":
    print(f"{len(MASTER_COLUMNS)} master columns, {len(SUPPLIERS)} suppliers")
