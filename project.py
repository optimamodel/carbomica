"""
Define atomica project based on input data spreadsheet.
"""
import atomica as at
import pandas as pd
from books import generate_books

## Time frame of simulation
start_year = 2024 # MODIFY AS NEEDED
end_year = start_year + 5 # MODIFY AS NEEDED

# Input data sheet file name (and path if applicable) and read facility code name
input_data_sheet = 'input_data_example.xlsx' # MODIFY AS NEEDED
facility_code = pd.read_excel(input_data_sheet, sheet_name='facility', index_col='Code Name').index[0]

# Generate framework, databook and progbook and return facility code name
generate_books(input_data_sheet, start_year, end_year)

# Atomica project definition
P = at.Project(framework = 'books/carbomica_framework_{}.xlsx'.format(facility_code), 
               databook = 'books/carbomica_databook_{}.xlsx'.format(facility_code), 
               do_run = False)

# Projection settings
P.settings.sim_dt    = 1 # simulation timestep
P.settings.sim_start = start_year # simulation start year
P.settings.sim_end   = end_year # simulation end year

# Load program and define variables for program runs
P.load_progbook('books/carbomica_progbook_{}.xlsx'.format(facility_code))

# Load co-benefits
cobenefits = pd.read_excel(input_data_sheet, sheet_name='interventions', index_col='Code Name').reindex(['Cost co-benefits','Other co-benefits'], axis=1)

# Load exclusions
try:
    exclusions = pd.read_excel(input_data_sheet, sheet_name='exclusions', header=None)
    exclusions = [{x for x in row if not pd.isna(x)} for _, row in exclusions.iterrows()]
except ValueError:
    exclusions = []

# Extract emissions parameters
emissions_pars = list(pd.read_excel(input_data_sheet, sheet_name='emission sources', index_col='Code Name').index)
