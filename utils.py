import matplotlib.pyplot as plt
import matplotlib as mpl
import pandas as pd
import atomica as at
import itertools
import sciris as sc

def calc_emissions(results, start_year, facility_code, file_name, title=None):
    '''
    Calculate emissions before and after program implementation, export results to Excel, and generate bar plots.
    :param results: list of Atomica result objects.
    :param start_year: Start year of simulations.
    :param facility_code: Code of the facility.
    :param file_name: Specify Excel file name for saving.
    :param title: Title for the plot.
    :return: DataFrame of emissions results.
    '''
    # Extract relevant parameter names for plotting
    pop = results[0].pop_names[0]
    pars = results[0].par_names(pop)
    parameters = [par for par in pars if '_mult' not in par and '_emissions' not in par and '_baseline' not in par]
    par_labels = [par.replace('_', ' ').title() for par in parameters]
    
    # Set up DataFrame for emissions
    rows = [res.name for res in results]
    df_emissions = pd.DataFrame(index=rows, columns=par_labels)
    start_i = list(results[0].t).index(start_year)
    
    # Populate the DataFrame with emissions data
    for par, par_label in zip(parameters, par_labels):
        for res in results:
            df_emissions.loc[res.name, par_label] = res.get_variable(par, facility_code)[0].vals[start_i]
    
    # Export the DataFrame to Excel
    writer_emissions = pd.ExcelWriter(f'results/{file_name}.xlsx', engine='xlsxwriter')
    df_emissions.to_excel(writer_emissions, sheet_name=facility_code)
    
    # Generate the bar plot
    fig_width = max(15, len(par_labels) * 1.5)
    fig_height = 10
    font_size = 22
    ax = df_emissions.plot(figsize=(fig_width, fig_height), kind='bar', stacked=True, fontsize=font_size)
    
    # Set plot title
    plt.title(title or 'Total CO2e Emissions', fontsize=font_size + 2)
    
    # Adjust legend
    ax.legend(title='Emission Sources', bbox_to_anchor=(1.0, 1.0), loc='upper left', fontsize=font_size-2, title_fontsize=font_size)
    
    # Format the y-axis
    ax.yaxis.set_major_formatter(mpl.ticker.StrMethodFormatter('{x:,.0f}'))
    
    # Adjust x-axis labels
    plt.xticks(rotation=90, ha='center')
    plt.ylabel('Emissions (CO2e)', fontsize=font_size)
    
    # Tight layout and save figure
    plt.tight_layout()
    plt.savefig(f'figs/{file_name}.png', bbox_inches='tight')
    plt.show()
    
    # Close the writer and release Excel file
    writer_emissions.close()
    
    print(f'Emissions results saved: results/{file_name}.xlsx')
    print(f'Emissions bar plots saved: figs/{file_name}.png')


def plot_allocation(df: pd.DataFrame) -> plt.Figure:
    '''
    Produces plot of allocation

    :param df: A dataframe where the index is the name of the scenario, and the columns are interventions. If a
               column called 'Surplus budget' is provided, it will be plotted with a hatched pattern
    :return: A matplotlib figure
    '''

    # Select colormap
    # colormap = plt.cm.tab20     # https://matplotlib.org/stable/users/explain/colors/colormaps.html#qualitative
    # colors = [colormap(i) for i in range(len(df.columns))]
    colors = sc.gridcolors(df.shape[1])

    fig, ax = plt.subplots()
    df.iloc[:,::-1].plot.bar(stacked=True, color=colors, ax=ax, fontsize=22)
    fig.set_size_inches(len(df)*2.5+6,10)

    # Apply hatched pattern to "Surplus budget" bars
    for bar, label in zip(ax.patches, df.columns[::-1].repeat(df.shape[0])):
        if label == "Surplus budget":
            bar.set_hatch('//')  # Applying hatched pattern

    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles[::-1], labels[::-1], loc='upper left', bbox_to_anchor=(1.05, 1), title='Interventions', fontsize=20, title_fontsize=22)
    ax.set_xticklabels([f"${x:,.0f}" for x in df.index], rotation=0)
    ax.yaxis.set_major_formatter(mpl.ticker.StrMethodFormatter('${x:,.0f}'))
    ax.set_title('Budget allocation', fontsize=25)
    ax.set_xlabel(None)
    fig.tight_layout()
    return fig


def plot_emissions(df: pd.DataFrame, title:str='Total CO2e Emissions') -> plt.Figure:
    """
    Plot emissions

    :param df: A dataframe where the index has the name of the scenario, and the columns are names of emissions sources
    :param title: The title to display on the plot
    :return: A matplotlib Figure
    """

    font_size = 22
    colors = None # sc.gridcolors(df.shape[1]) # Original code had no special colormap

    fig, ax = plt.subplots()
    df.iloc[:, ::-1].plot.bar(stacked=True, color=colors, ax=ax, fontsize=font_size)

    plt.title(title, fontsize=font_size + 2)

    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles[::-1], labels[::-1], title='Emission Sources', bbox_to_anchor=(1.0, 1.0), loc='upper left', fontsize=font_size - 2, title_fontsize=font_size)

    ax.yaxis.set_major_formatter(mpl.ticker.StrMethodFormatter('{x:,.0f}'))
    ax.set_xticklabels([f"${x:,.0f}" if sc.isnumber(x) else x for x in df.index], ha='center', rotation=90)
    ax.set_xlabel(None)
    ax.set_ylabel('Emissions (CO2e)', fontsize=font_size)

    fig.set_size_inches(max(15, len(df) * 1.5), 10)
    fig.tight_layout()

    return fig


def write_alloc_excel(progset, results, year, print_results=True,file_name=None):
    """Write optimized budget allocations onto an excel file
        :param: P: atomica project
        :param: results: results from optimization runs
        :param: save_dir: path for saving the plot
        :param: name to be given to excel file (string)
        """
        
    progname = []
    prog_labels = []
    for prog in progset.programs:
        progname += [prog]
        prog_labels += [progset.programs[prog].label]
        
    bars = []
    for i in range(0, len(results)):
         bar_name = results[i].name
         bars.append(bar_name)
         
    d1 = at.PlotData.programs(results, quantity='spending')
    d1.interpolate(year)
    spending_raw_data = {(x.result, x.output): x.vals[0] for x in d1.series}
    spending_data = {res: {prog:0 for prog in progname} for res in bars}
    
    d2 = at.PlotData.programs(results, quantity='coverage_fraction')
    d2.interpolate(year)
    cov_raw_data = {(x.result, x.output): x.vals[0] for x in d2.series}
    cov_data = {res: {prog:0 for prog in progname} for res in bars}
    for br in bars:
        for prog in progname:
            spending_data[br][prog] = spending_raw_data[(br, prog)]
            cov_data[br][prog] = cov_raw_data[(br, prog)]
    df1 = pd.DataFrame(spending_data)
    df2 = pd.DataFrame(cov_data)
    df1.index = prog_labels
    df2.index = prog_labels
    
    if print_results:
        file_name = file_name+'.xlsx'
        writer = pd.ExcelWriter(file_name, engine='xlsxwriter')
        df1.to_excel(writer, sheet_name="Budgets")
        df2.to_excel(writer, sheet_name="Coverages")
        writer.close()
        print('Excel file saved: {}'.format(file_name))
    
    return df1, df2

def powerset(set):
    """
    Return all combinations of length 0-n

    For example, given the collection [1,2,3] this function would return
    [],[1],[2],[3],[1,2],[1,3],[2,3],[1,2,3]

    :param set: Iterable of items (set, list)
    :return: Generator of all combinations
    """
    return itertools.chain.from_iterable(itertools.combinations(set, r) for r in range(len(set) + 1))

def is_forbidden_combination(combo, forbidden=None):
    """
    Check if a given set of programs contains a subset of programs that is forbidden
    :param combo: List of programs
    :param forbidden: List of forbidden program combinations
    :return: Boolean, True if program list contains a forbidden combination
    """
    if forbidden is not None:
        for f in forbidden:
            if len(f & set(combo)) > 1:
                return True
    return False
