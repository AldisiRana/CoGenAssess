# -*- coding: utf-8 -*-
import re

import click
import shutil

import pandas as pd
import numpy as np
from scipy.stats import pearsonr
from tqdm import tqdm

from .utils import get_gene_info, plink_process, combine_scores
from .pipeline import normalize_gene_len, find_pvalue, betareg_pvalues, r_visualize, merge_files_fun


#TO DO:
#Word args better
#Fix pipeline -> calc pvals
#update README
@click.group()
def main():
    """Handle cogenassess functions."""


@main.command()
@click.option('-a', '--annotated-file', required=True, help='the annotated file')
@click.option('--bed', required=True)
@click.option('--bim', required=True)
@click.option('--fam', required=True)
@click.option('--plink', default='plink')
@click.option('-t', '--temp-dir', required=True)
@click.option('-o', '--output-file', required=True)
@click.option('--beta-param', default=(1.0, 25.0), nargs=2, type=float)
@click.option('--weight-func', default='beta', type=click.Choice(['beta', 'log10']))
@click.option('--variant-col', default='SNP')
@click.option('--gene-col', default='Gene.refGene')
@click.option('--af-col', default='MAF')
@click.option('--del-col', default='CADD_raw')
@click.option('--alt-col', default='Alt')
@click.option('--maf-threshold', default=0.01)
@click.option('--remove-temp', is_flag=True)
def score_genes(
    annotated_file,
    bed,
    bim,
    fam,
    plink,
    beta_param,
    temp_dir,
    output_file,
    weight_func,
    variant_col,
    gene_col,
    af_col,
    del_col,
    alt_col,
    maf_threshold,
    remove_temp,
):
    """
    Get genes' scores using annotated vcf.

    :param vcf: a vcf with annotations. use vcfanno.
    :param bed: test file for genotype.
    :param bim: file with variant information
    :param fam: text file for pedigree information
    :param plink: the directory of plink, if not set in environment
    :param beta_param: the parameters from beta weight function.
    :param temp_dir: a temporary directory to save temporary files before merging.
    :param output_file: the final output scores matrix.
    :param weight_func: the weighting function used in score calculation.
    :param remove_temp: if True temporary directory will be deleted after process completion.
    :return: the final dataframe information.
    """
    click.echo('getting information from vcf files')
    genes_folder = get_gene_info(
        annotated_file=annotated_file,
        output_dir=temp_dir,
        beta_param=beta_param,
        weight_func=weight_func,
        del_col=del_col,
        maf_threshold=maf_threshold,
        genes_col=gene_col,
        variant_col=variant_col,
        af_col=af_col,
        alt_col=alt_col,
    )
    click.echo('calculating gene scores ...')
    plink_process(genes_folder=genes_folder, plink=plink, bed=bed, bim=bim, fam=fam)
    click.echo('combining score files ...')
    df = combine_scores(input_path=temp_dir, output_path=output_file)
    if remove_temp:
        shutil.rmtree(temp_dir)
    click.echo('process is complete.')
    return df.info()


@main.command()
@click.option('--bed', required=True)
@click.option('--bim', required=True)
@click.option('--fam', required=True)
@click.option('--plink', default='plink')
@click.option('--genes-folder', required=True)
def run_plink(*, genes_folder, plink, bed, bim, fam):
    """
    Get the genes' scores from a folder of genes info.
    :param genes_folder: a folder that contains two files for each gene,
    one containing gene and ID (.v) and the other containing the rest of the information (.w)
    :param plink: the directory of plink, if not set in environment
    :param bed: test file for genotype.
    :param bim: file with variant information
    :param fam: text file for pedigree information
    :return:
    """
    click.echo('staring plink processing ...')
    plink_process(genes_folder=genes_folder, plink=plink, bed=bed, bim=bim, fam=fam)
    click.echo('plink processing is complete.')


@main.command()
@click.option('-s', '--scores-file', required=True, help="The scoring file of genes across a population.")
@click.option('-i', '--genotype-file', required=True, help="File containing information about the cohort.")
@click.option('-o', '--output-path', required=True, help='the path for the output file.')
@click.option('-g', '--genes',
              help="a list containing the genes to calculate. if not provided all genes will be used.")
@click.option('-t', '--test', required=True,
              type=click.Choice(['ttest_ind', 'mannwhitneyu', 'logit', 'glm', 'betareg']),
              help='statistical test for calculating P value.')
@click.option('-c', '--cases-column', required=True, help="the name of the column that contains the case/control type.")
@click.option('-m', '--samples-column', required=True, help="the name of the column that contains the samples.")
@click.option('-p', '--pc-file', default=None, help="Principle components values for logistic regression.")
@click.option('--adj-pval', type=click.Choice(
    ['bonferroni', 'sidak', 'holm-sidak', 'holm',
     'simes-hochberg', 'hommel', 'fdr_bh', 'fdr_by', 'fdr_tsbh', 'fdr_tsbky']))
@click.option('--covariates', default='PC1,PC2', help="the covariates used for calculation")
def calculate_pval(
    *,
    scores_file,
    genotype_file,
    output_path,
    genes,
    cases_column,
    samples_column,
    test,
    pc_file,
    adj_pval,
    covariates,
):
    """
    Calculate the P-value between two given groups.
    :param scores_file: the file containing gene scores.
    :param genotype_file: file containing the phenotype.
    :param output_path: the path for final output.
    :param genes: a list of genes to calculate. if not, all genes in scoring file will be used.
    :param cases_column: the name of the column with phenotypes.
    :param samples_column: the name of the column with sample IDs. All files need to have the same format.
    :param test: the test used to calculate pvalue.
    :param pc_file: the file with PC (alternatively the file with covariates to use in test).
    :param adj_pval: the adjustment method used (if any).
    :param covariates: the column names of covariates to use, with comma in between. (e.g: PC1,PC2,age)
    :return:
    """
    if test == 'betareg':
        betareg_pvalues(
            scores_file=scores_file,
            pheno_file=genotype_file,
            cases_col=cases_column,
            samples_col=samples_column,
            output_path=output_path,
            covariates=covariates
        )
    else:
        scores_df = pd.read_csv(scores_file, sep=r'\s+')

        click.echo("The process for calculating the p_values will start now.")
        df = find_pvalue(
            scores_df=scores_df,
            output_file=output_path,
            genotype_file=genotype_file,
            genes=genes,
            cases_column=cases_column,
            samples_column=samples_column,
            test=test,
            pc_file=pc_file,
            adj_pval=adj_pval,
        )
        click.echo('Process is complete.')
        click.echo(df.info())


@main.command()
@click.option('-i', '--input-path', required=True, help="The directory that contains the matrices to merge.")
@click.option('-o', '--output-path', required=True, help='the path for the output file.')
@click.option('-r', '--remove-input', is_flag=True, help='if flagged will remove input folder')
def merge(
    *,
    output_path,
    input_path,
    remove_input,
):
    """
    This command merges all matrices in a directory into one big matrix.
    :param output_path: the path of final merged matrix
    :param input_path: the directory containing the matrices to merge.
    :param remove_input: if True, the input directory will be removed after merge.
    :return:
    """
    click.echo("Starting the merging process")
    df = combine_scores(input_path=input_path, output_path=output_path)
    click.echo(df.info())
    if remove_input:
        shutil.rmtree(input_path)
    click.echo("Merging is done.")


@main.command()
@click.option('-m', '--matrix-file', required=True, help="The scoring matrix to normalize.")
@click.option('-g', '--genes-lengths-file',
              help="The file containing the lengths of genes. If not provided it will be produced.")
@click.option('-o', '--output-path', required=True, help='the path for the output file.')
@click.option('-s', '--samples-col', default='IID', help='the name of the samples column')
def normalize(
    *,
    matrix_file,
    genes_lengths_file=None,
    output_path=None,
    samples_col
):
    """This command normalizes the scoring matrix by gene length."""
    click.echo("Normalization in process.")
    normalize_gene_len(
        matrix_file=matrix_file,
        genes_lengths_file=genes_lengths_file,
        output_path=output_path,
        samples_col=samples_col
    )


@main.command()
@click.option('--first-file', required=True)
@click.option('--second-file', required=True)
@click.option('--samples-col', default='IID')
@click.option('--output-file', required=True)
def calc_corr(
    *,
    first_file,
    second_file,
    samples_col,
    output_file,
):
    """Calculate the pearson's correlation between same genes in two scoring matices."""
    with open(first_file) as f:
        genes_01 = re.split('\s+', f.readline().strip('\n'))
        genes_01.remove(samples_col)
    with open(second_file) as f:
        genes_02 = re.split('\s+', f.readline().strip('\n'))
        genes_02.remove(samples_col)
    as_set = set(genes_01)
    common_genes = as_set.intersection(genes_02)
    genes = list(common_genes)
    corr_info = []
    first_df = pd.read_csv(first_file, sep=r'\s+', index_col=False)
    second_df = pd.read_csv(second_file, sep=r'\s+', index_col=False)
    for gene in tqdm(genes, desc='calculating correlation'):
        gene_df = pd.merge(first_df[[samples_col, gene]], second_df[[samples_col, gene]], on=samples_col)
        gene_df.replace([np.inf, -np.inf, np.nan], 0.0, inplace=True)
        corr, pval = pearsonr(gene_df[gene + '_x'], gene_df[gene + '_y'])
        corr_info.append([gene, corr, pval])
    corr_df = pd.DataFrame(corr_info, columns=['genes', 'corr', 'p_value']).sort_values(by=['p_value'])
    corr_df.to_csv(output_file, sep='\t', index=False)
    click.echo('Process is complete.')
    click.echo(corr_df.info())


@main.command()
@click.option('--pvals-file', required=True)
@click.option('--info-file', required=True)
@click.option('--genescol-1', default='gene')
@click.option('--genescol-2', default='Gene.refGene')
@click.option('--qq-output', required=True)
@click.option('--manhattan-output', required=True)
@click.option('--pvalcol', default='p_value')
def visualize(
    pvals_file,
    info_file,
    genescol_1,
    genescol_2,
    qq_output,
    manhattan_output,
    pvalcol,
):
    r_visualize(
        pvals_file=pvals_file,
        info_file=info_file,
        genescol_1=genescol_1,
        genescol_2=genescol_2,
        qq_output=qq_output,
        manhattan_output=manhattan_output,
        pvalcol=pvalcol,
    )


@main.command()
@click.option('-d', '--input-dir', required=True)
@click.option('-o', '--output-file', required=True)
@click.option('-s', '--samples-col', required=True)
@click.option('-e', '--extension', required=True, type=click.Choice(['pickle', 'feather', 'tsv']))
def merge_files(
    *,
    input_dir,
    output_file,
    samples_col,
    extension
):
    df = merge_files_fun(input_dir=input_dir, samples_col=samples_col)
    if extension == 'pickle':
        df.to_pickle(output_file)
    elif extension == 'feather':
        df.reset_index().to_feather(output_file)
    # if df.memory_usage(deep=True).sum() / float(1 << 30) > 10:
    #   df.to_feather(output_file)
    #  df.to_pickle(output_file)
    else:
        df.to_csv(output_file, sep='\t', index=False)
    return df.info


def prediction_model(
    *,
    data,
    labels,

):
    pass

if __name__ == '__main__':
    main()
