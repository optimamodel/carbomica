import atomica as at
import pandas as pd
import os
import numpy as np
import itertools

if not os.path.exists('books'): os.makedirs('books')
'''
Function to generate a framework, databook and progbook.
'''

def generate_books(input_data_sheet, start_year, end_year):
    '''
    Generate framework, databook and progbook based on input data sheet.
    Results on emission reductions are saved in an excel sheet.
    :param input_data_sheet: file name of input data sheet.
    :param start_year: Start year of simulations.
    :param facility_code: Code of the facility.
    :return: 
    '''
    facility_code = pd.read_excel(input_data_sheet, sheet_name='facility', index_col='Code Name')
    facility = {}
    facility[facility_code.index[0]] = {'label': facility_code.loc[facility_code.index[0],'Display Name'], 'type': 'facilities'}
    
    facility_code = facility_code.index[0]
    
    interventions_list = pd.read_excel(input_data_sheet, sheet_name='interventions', index_col='Code Name')
    interventions = {}
    for intervention in interventions_list.index:
        interventions[intervention] = interventions_list.loc[intervention,'Display Name']
    
    ## Step 1: read in base framework, and generate intervention-specific parameters 
    # read framework base from template
    df_fw = pd.read_excel(pd.ExcelFile('templates/carbomica_framework_template.xlsx'), sheet_name=None)
    emissions_list = pd.read_excel(input_data_sheet, sheet_name='emission sources', index_col='Code Name')
    
    # define intervention-specific parameters and add to the Parameters sheet as a new row
    for i, emission in enumerate(emissions_list.index):
        emission_par = {'Code Name': emission+'_baseline', 
                    'Display Name': emissions_list.loc[emission,'Display Name'] + ' - baseline',
                    'Targetable': 'n',
                    'Databook Page': 'emission_sources'} # define coverage of intervention as a new row in framework
        emission_mult = {'Code Name': emission+'_mult', 
                    'Display Name': emissions_list.loc[emission,'Display Name'] + ' - multiplier',
                    'Targetable': 'y',
                    'Default Value': 0,
                    'Minimum Value': 0,
                    'Maximum Value': 1,
                    'Databook Page': 'targeted_pars'}
        emission_actual = {'Code Name': emission, 
                'Display Name': emissions_list.loc[emission,'Display Name'],
                'Targetable': 'n',
                'Population type': 'facilities',
                'Function': emission_par['Code Name']+'*(1-'+emission_mult['Code Name']+')'} # define coverage of intervention as a new row in framework
        df_fw['Parameters'] = pd.concat([df_fw['Parameters'], pd.DataFrame([emission_par])], ignore_index=True)
        df_fw['Parameters'] = pd.concat([df_fw['Parameters'], pd.DataFrame([emission_mult])], ignore_index=True)
        df_fw['Parameters'] = pd.concat([df_fw['Parameters'], pd.DataFrame([emission_actual])], ignore_index=True)
        # update the function for total emissions:
        if i == 0:
            df_fw['Parameters'].loc[df_fw['Parameters']['Code Name']=='co2e_emissions','Function'] = emission_actual['Code Name']
        else:
            df_fw['Parameters'].loc[df_fw['Parameters']['Code Name']=='co2e_emissions','Function'] += '+'+emission_actual['Code Name']
        
    with pd.ExcelWriter('books/carbomica_framework_{}.xlsx'.format(facility_code)) as writer:
        for sheet_name, df in df_fw.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    
    ## Step 2: generate and populate the databook (saved in "books/")
    F = at.ProjectFramework('books/carbomica_framework_{}.xlsx'.format(facility_code))  # load framework
    data_years = np.arange(start_year, end_year) # years for input data
    
    D = at.ProjectData.new(framework=F, tvec=data_years, pops=facility, transfers=0)
    db_data = pd.read_excel(input_data_sheet, sheet_name='emission data', index_col='facilities')
    cols_to_drop = [col for col in db_data.columns if 'Unnamed' in col]
    db_data.drop(columns=cols_to_drop,inplace=True)

    D.tdve['facilities_number'].ts[facility_code] = at.TimeSeries(data_years, 1, units='Number')
    D.tdve['facilities_number'].write_assumption = True
    for parameter in db_data.columns:
        D.tdve[parameter+'_baseline'].ts[facility_code] = at.TimeSeries(data_years, db_data.loc[facility_code,parameter])
        D.tdve[parameter+'_baseline'].write_assumption = True
            
    D.save('books/carbomica_databook_{}.xlsx'.format(facility_code))
        
    ## Step 3: generate empty progbooks in folder "templates/"
    databook_name = 'books/carbomica_databook_{}.xlsx'.format(facility_code)
    P = at.Project(framework=F,databook=databook_name, do_run=False)
    progbook_path = 'books/carbomica_progbook_{}.xlsx'.format(facility_code)
    data_years = np.arange(start_year, end_year) # years for program data (offset by 1 year compared to databook)
    P.make_progbook(progbook_path,progs=interventions,data_start=data_years[0],data_end=data_years[-1])
        
    target_pars_overall = pd.read_excel(input_data_sheet, sheet_name='emission targets', index_col='interventions')
    cols_to_drop = [col for col in target_pars_overall.columns if 'Unnamed' in col]
    target_pars_overall.drop(columns=cols_to_drop,inplace=True)
    
    effects = pd.read_excel(input_data_sheet, sheet_name='effect sizes', index_col='facilities')
    cols_to_drop = [col for col in effects.columns if 'Unnamed' in col]
    effects.drop(columns=cols_to_drop,inplace=True)
    
    # Populate the progbooks that were just created and save the files to "books/"
    D = at.ProjectData.from_spreadsheet(databook_name,framework=F) 
    pb_costs_maintain = pd.read_excel(input_data_sheet, sheet_name='maintenance costs', index_col='facilities') 
    cols_to_drop = [col for col in pb_costs_maintain.columns if 'Unnamed' in col]
    pb_costs_maintain.drop(columns=cols_to_drop,inplace=True) 
    pb_costs_implement = pd.read_excel(input_data_sheet, sheet_name='implementation costs', index_col='facilities') 
    cols_to_drop = [col for col in pb_costs_implement.columns if 'Unnamed' in col]
    pb_costs_implement.drop(columns=cols_to_drop,inplace=True) 
    P = at.ProgramSet.from_spreadsheet(spreadsheet='books/carbomica_progbook_{}.xlsx'.format(facility_code), framework=F, data=D, _allow_missing_data=True)
    for intervention in interventions:
        # Write in 'Program targeting' sheet
        P.programs[intervention].target_pops = [facility_code]
        P.programs[intervention].target_comps = ['facilities_number']
        
        # Write in 'Spending data' sheet
        P.programs[intervention].unit_cost = at.TimeSeries(assumption=pb_costs_implement.loc[facility_code,intervention+'_cost']/len(data_years)+pb_costs_maintain.loc[facility_code,intervention+'_cost'], units='$/person/year')
        P.programs[intervention].spend_data = at.TimeSeries(data_years,0, units='$/year')
        P.programs[intervention].capacity_constraint = at.TimeSeries(units='people')
        P.programs[intervention].coverage = at.TimeSeries(units='people')
            
        # Write in 'Program effects' sheet
        target_pars_overall_t = target_pars_overall.transpose()
        for par in target_pars_overall_t.index:
            target_interventions = target_pars_overall_t.columns[target_pars_overall_t.loc[par]=='y'].tolist()
            progs = {}
            for intervention in target_interventions:
                effect = effects.loc[facility_code,intervention+'_effect']
                progs[intervention] = effect
            P.covouts[(par+'_mult', facility_code)] = at.programs.Covout(par=par+'_mult',pop=facility_code,cov_interaction='random',baseline=0,progs=progs)
        P.programs[intervention].spend_data = at.TimeSeries(data_years,0, units='$/year') # make initial spending a small, negligible but non-zero number for optimisation initialisation


    # Explicitly set combined outcomes
    powerset = lambda x: itertools.chain.from_iterable(itertools.combinations(x, r) for r in range(len(x) + 1))
    for covout in P.covouts.values():
        s = []
        for combo in powerset(covout.progs):
            if not combo:
                continue
            v = 0
            for prog in combo:
                v += covout.progs[prog]
            s.append('+'.join(combo)+'='+str(v))
        covout.imp_interaction = ','.join(s)

    # Save final progbook
    P.save('books/carbomica_progbook_{}.xlsx'.format(facility_code))
        