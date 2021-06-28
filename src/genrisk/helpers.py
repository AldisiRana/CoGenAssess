# -*- coding: utf-8 -*-
import multiprocessing
import re
from functools import partial

import numpy as np
import pandas as pd
import statsmodels.api as sm
import scipy.stats as stats
from tqdm import tqdm


def run_linear(gene_col, x_set, y_set):
    """
    Helper function to run linear regression association.

    :param gene_col: a tuple from df.iteritems()
    :param x_set: the covariates.
    :param y_set: the target.

    :return: a list with gene name, pvalues, coefs and std err.
    """
    x_set[gene_col[0]] = gene_col[1]
    x_set = sm.add_constant(x_set)
    linear_model = sm.OLS(y_set, x_set)
    result = linear_model.fit()
    pval = list(result.pvalues)
    beta_coef = list(result.params)[-1]
    std_err = result.bse[-1]
    return [gene_col[0]] + pval + [beta_coef, std_err]


def run_logit(gene_col, x_set, y_set):
    """
    Helper function to run logistic regression association.

    :param gene_col: a tuple from df.iteritems()
    :param x_set: the covariates.
    :param y_set: the target.

    :return: a list with gene name, pvalues, and std err.
    """
    x_set[gene_col[0]] = gene_col[1]
    x_set = sm.add_constant(x_set)
    logit_model = sm.Logit(y_set, x_set)
    result = logit_model.fit()
    pval = list(result.pvalues)
    std_err = result.bse[-1]
    return [gene_col[0]] + pval + [std_err]


def uni_profiles(df, f):
    """
    Merge two dataframes.

    :param df: the main dataframe with all the scores.
    :param f: the file containing the scores of one gene.

    :return: the merged dataframe.
    """
    df2 = pd.read_csv(str(f), usecols=['IID', 'SCORESUM'], sep=r'\s+').astype({'SCORESUM': np.float32})
    r = re.compile("([a-zA-Z0-9_.-]*).profile$")
    gene2 = r.findall(str(f))
    df2.rename(columns={'SCORESUM': gene2[0]}, inplace=True)
    df = pd.merge(df, df2, on='IID')
    return df


def run_mannwhitneyu(**kwargs):
    p_values = []
    df_by_cases = kwargs['df'].groupby(kwargs['cases_column'])
    if kwargs['cases'] and kwargs['controls']:
        cc = [kwargs['cases'], kwargs['controls']]
    else:
        cc = list(df_by_cases.groups.keys())
    if len(cc) > 2:
        Warning('There are more than two categories here. We will only consider the first two categories.')
    for gene in tqdm(kwargs['genes'], desc='Calculating p_values for genes'):
        case_0 = df_by_cases.get_group(cc[0])[gene].tolist()
        case_1 = df_by_cases.get_group(cc[1])[gene].tolist()
        try:
            u_statistic, p_val = stats.mannwhitneyu(case_0, case_1, alternative='greater')
        except:
            continue
        p_values.append([gene, u_statistic, p_val])
    cols = ['genes', 'statistic', 'p_value']
    p_values_df = pd.DataFrame(p_values, columns=cols).sort_values(by=['p_value'])
    return p_values_df


def run_ttest(**kwargs):
    p_values = []
    df_by_cases = kwargs['df'].groupby(kwargs['cases_column'])
    if kwargs['cases'] and kwargs['controls']:
        cc = [kwargs['cases'], kwargs['controls']]
    else:
        cc = list(df_by_cases.groups.keys())
    if len(cc) > 2:
        Warning('There are more than two categories here. We will only consider the first two categories.')

    for gene in tqdm(kwargs['genes'], desc='Calculating p_values for genes'):
        case_0 = df_by_cases.get_group(cc[0])[gene].tolist()
        case_1 = df_by_cases.get_group(cc[1])[gene].tolist()
        try:
            statistic, p_val = stats.ttest_ind(case_0, case_1)
        except:
            continue
        p_values.append([gene, statistic, p_val])
    cols = ['genes', 'statistic', 'p_value']
    p_values_df = pd.DataFrame(p_values, columns=cols).sort_values(by=['p_value'])
    return p_values_df


def get_pvals_logit(**kwargs):
    cases_column = kwargs['cases_column']
    genes = kwargs['genes']
    covariates = kwargs['covariates']
    kwargs['df'][cases_column] = np.interp(
        kwargs['df'][cases_column], (kwargs['df'][cases_column].min(), kwargs['df'][cases_column].max()), (0, 1))
    y_set = kwargs['df'][[cases_column]]
    x_set = kwargs['df'][covariates]
    genes_df = kwargs['df'][genes]
    pool = multiprocessing.Pool(processes=kwargs['processes'])
    partial_func = partial(run_logit, x_set=x_set, y_set=y_set)
    p_values = list(pool.imap(partial_func, genes_df.iteritems()))
    cols = ['genes', 'const_pval'] + covariates + ['p_value', 'std_err']
    p_values_df = pd.DataFrame(p_values, columns=cols).sort_values(by=['p_value'])
    return p_values_df


def get_pvals_linear(**kwargs):
    cases_column = kwargs['cases_column']
    genes = kwargs['genes']
    covariates = kwargs['covariates']
    y_set = kwargs['df'][[cases_column]]
    x_set = kwargs['df'][covariates]
    genes_df = kwargs['df'][genes]
    pool = multiprocessing.Pool(processes=kwargs['processes'])
    partial_func = partial(run_linear, x_set=x_set, y_set=y_set)
    p_values = list(pool.imap(partial_func, genes_df.iteritems()))
    cols = ['genes', 'const_pval'] + covariates + ['p_value', 'beta_coef', 'std_err']
    p_values_df = pd.DataFrame(p_values, columns=cols).sort_values(by=['p_value'])
    return p_values_df

