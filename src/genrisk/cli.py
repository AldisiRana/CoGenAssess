# -*- coding: utf-8 -*-
import os
import shutil
import subprocess

import click
import pandas as pd
from sklearn.model_selection import train_test_split

from .pipeline import find_pvalue, betareg_pvalues, create_prediction_model, model_testing
from .utils import get_gene_info, plink_process, combine_scores, download_pgs, draw_qqplot, draw_manhattan


@click.group()
def main():
    """Handle genrisk functions."""


@main.command()
@click.option('-a', '--annotated-vcf', required=True, help='the annotated vcf')
@click.option('-b', '--bfiles', default=None)
@click.option('--plink', default='plink', help="the directory of plink, if not set in environment")
@click.option('-t', '--temp-dir', required=True, help="a temporary directory to save temporary files before merging.")
@click.option('-o', '--output-file', required=True, help="the final output scores matrix.")
@click.option('--beta-param', default=(1.0, 25.0), nargs=2, type=float,
              help="the parameters from beta weight function.")
@click.option('--weight-func', default='beta', type=click.Choice(['beta', 'log10']),
              help="the weighting function used in score calculation.")
@click.option('--variant-col', default='SNP', help="the column containing the variant IDs.")
@click.option('--gene-col', default='Gene.refGene', help="the column containing gene names.")
@click.option('--af-col', default='MAF', help="the column containing allele frequency.")
@click.option('--del-col', default='CADD_raw', help="the column containing the deleteriousness score.")
@click.option('--alt-col', default='Alt', help="the column containing the alternate base.")
@click.option('--maf-threshold', default=0.01, help="the threshold for minor allele frequency.")
def score_genes(
    *,
    annotated_vcf,
    bfiles,
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
):
    """
    Calculate the gene-based scores for a given dataset.

    :param annotated_vcf: an annotated containing variant IDs, alt, info and samples genotypes.
    :param plink: the directory of plink, if not set in environment
    :param beta_param: the parameters from beta weight function.
    :param temp_dir: a temporary directory to save temporary files before merging.
    :param output_file: the final output scores matrix.
    :param weight_func: the weighting function used in score calculation.
    :param variant_col: the column containing the variant IDs.
    :param gene_col: the column containing gene names.
    :param af_col: the column containing allele frequency.
    :param del_col: the column containing deleteriousness score.
    :param alt_col: the column containing alternate base.
    :param maf_threshold: the threshold for minor allele frequency.

    :return: the final dataframe information.
    """
    confirm = click.confirm('Would you like us to delete the temporary files when process is done?')
    click.echo('getting information from vcf files')
    genes_folder = get_gene_info(
        annotated_vcf=annotated_vcf,
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
    plink_process(genes_folder=genes_folder, plink=plink, annotated_vcf=annotated_vcf, bfiles=bfiles)
    click.echo('combining score files ...')
    df = combine_scores(input_path=temp_dir, output_path=output_file)
    if confirm:
        shutil.rmtree(temp_dir)
    click.echo('process is complete.')
    return df.info()


@main.command()
@click.option('-s', '--scores-file', required=True, help="The scoring file of genes across a population.")
@click.option('-i', '--info-file', required=True, help="File containing information about the cohort.")
@click.option('-o', '--output-path', required=True, help='the path for the output file.')
@click.option('-g', '--genes',
              help="a list containing the genes to calculate. if not provided all genes will be used.")
@click.option('-t', '--test', required=True,
              type=click.Choice(['ttest_ind', 'mannwhitneyu', 'logit', 'glm', 'betareg', 'linear']),
              help='statistical test for calculating P value.')
@click.option('-c', '--cases-column', required=True,
              help="the name of the column that contains the case/control or quantitative vals.")
@click.option('-m', '--samples-column', required=True, help="the name of the column that contains the samples.")
@click.option('--adj-pval', type=click.Choice(
    ['bonferroni', 'sidak', 'holm-sidak', 'holm',
     'simes-hochberg', 'hommel', 'fdr_bh', 'fdr_by', 'fdr_tsbh', 'fdr_tsbky']))
@click.option('--covariates', default='PC1,PC2', help="the covariates used for calculation")
@click.option('-p', '--processes', type=int, default=1, help='number of processes for parallelization')
def find_association(
    *,
    scores_file,
    info_file,
    output_path,
    genes,
    cases_column,
    samples_column,
    test,
    adj_pval,
    covariates,
    processes,
):
    """
    Calculate the P-value between two given groups.

    :param scores_file: the file containing gene scores.
    :param info_file: file containing the phenotype.
    :param output_path: the path for final output.
    :param genes: a list of genes to calculate. if not, all genes in scoring file will be used.
    :param cases_column: the name of the column with phenotypes.
    :param samples_column: the name of the column with sample IDs. All files need to have the same format.
    :param test: the test used to calculate pvalue.
    :param adj_pval: the adjustment method used (if any).
    :param covariates: the column names of covariates to use, with comma in between. (e.g: PC1,PC2,age)
    :param processes: number of processes for parallelization.

    :return:
    """
    if test == 'betareg':
        betareg_pvalues(
            scores_file=scores_file,
            pheno_file=info_file,
            cases_col=cases_column,
            samples_col=samples_column,
            output_path=output_path,
            covariates=covariates,
            processes=processes,
        )
    else:
        click.echo("The process for calculating the p_values will start now.")
        df = find_pvalue(
            scores_file=scores_file,
            output_file=output_path,
            info_file=info_file,
            genes=genes,
            cases_column=cases_column,
            samples_column=samples_column,
            test=test,
            adj_pval=adj_pval,
            covariates=covariates,
            processes=processes,
        )
        click.echo('Process is complete.')
        click.echo(df.info())


@main.command()
@click.option('-p', '--pvals-file', required=True, help="the file containing p-values.")
@click.option('-i', '--info-file', help="file containing variant/gene info.")
@click.option('--genescol-1', default='gene', help="the name of the genes column in pvals file.")
@click.option('--genescol-2', default='Gene.refGene', help="the name of the genes column in info file.")
@click.option('-q', '--qq-output', default=None, help="the name of the qq plot file.")
@click.option('-m', '--manhattan-output', default=None, help="the name of the manhatten plot file.")
@click.option('-v', '--pval-col', default='p_value', help="the name of the pvalues column.")
@click.option('-c', '--chr-col', default='Chr', help='the name of the chromosomes column')
@click.option('-s', '--pos-col', default='Start', help='the name of the position/start of the gene column')
def visualize(
    pvals_file,
    info_file,
    genescol_1,
    genescol_2,
    qq_output,
    manhattan_output,
    pval_col,
    chr_col,
    pos_col,
):
    """
    Visualize manhatten plot and qqplot for the data.

    :param pvals_file: the file containing p-values.
    :param info_file: file containing variant/gene info.
    :param genescol_1: the name of the genes column in pvals file.
    :param genescol_2: the name of the genes column in info file.
    :param qq_output: the name of the qq plot file.
    :param manhattan_output: the name of the manhatten plot file.
    :param pval_col: the name of the pvalues column.
    :param pos_col: the name of the position/start column.
    :param chr_col: the name of chromosomes column.

    :return:

    """
    pvals_df = pd.read_csv(pvals_file, sep='\t', index_col=False)
    if qq_output:
        draw_qqplot(pvals=pvals_df[pval_col], qq_output=qq_output)
    if manhattan_output:
        if not info_file:
            raise Exception('Please provide a file with gene information to generate manhattan plot.')
        info_df = pd.read_csv(info_file, sep="\t", index_col=False)
        merged = pd.merge(pvals_df, info_df, left_on=genescol_1, right_on=genescol_2, how='inner')
        draw_manhattan(
            data=merged,
            chr_col=chr_col,
            pos_col=pos_col,
            pvals_col=pval_col,
            genes_col=genescol_1,
            manhattan_output=manhattan_output
        )


@main.command()
@click.option('--data-file', required=True, help='file with all features and target for training model.')
@click.option('--output-folder', required=True, help='path of folder that will contain all outputs.')
@click.option('--test-size', default=0.25, help='test size for cross validation and evaluation.')
@click.option('--test', is_flag=True,
              help='if flagged, a test set will be created for evaluating the final model.')
@click.option('--model-name', required=True, help='name of model file.')
@click.option('--model-type', required=True, type=click.Choice(['regressor', 'classifier']),
              help='type of prediction model.')
@click.option('--target-col', required=True, help='name of target column in data_file.')
@click.option('--imbalanced', is_flag=True, help='if flagged methods will be used to account for the imbalance.')
@click.option('--normalize', is_flag=True, help='if flagged the data will be normalized before training.')
@click.option('--folds', default=10, type=int, help='number of cross-validation folds in training.')
@click.option('--metric', help='the metric used to choose best model after training.')
@click.option('--samples-col', default='IID')
def create_model(
    *,
    data_file,
    output_folder,
    test_size=None,
    test,
    model_name,
    model_type,
    target_col,
    imbalanced,
    normalize,
    folds,
    metric,
    samples_col,
):
    """
    Create a machine learning model with given dataset.

    :param samples_col: the name of the column with samples identifiers.
    :param data_file: file containing features and target.
    :param output_folder: a folder path to save all outputs.
    :param test_size: the size of testing set.
    :param test: if True the dataset will be split into training and testing for extra evaluation after finalization.
    :param model_name: the name of the model to be saved.
    :param model_type: the type of model (regressor or classifier).
    :param target_col: the name of the target column in data file.
    :param imbalanced: if true methods will be used to account for the imbalance.
    :param normalize:  if true the data will be normalized before training
    :param folds: the number of folds used for cross validation
    :param metric: the metric used to choose best model after training.

    :return: the final model
    """
    training_set = pd.read_csv(data_file, sep='\t', index_col=samples_col)
    testing_set = pd.DataFrame()
    if test:
        training_set, testing_set = train_test_split(training_set, test_size=test_size)
    os.mkdir(output_folder)
    os.chdir(output_folder)
    model = create_prediction_model(
        model_name=model_name,
        model_type=model_type,
        imbalanced=imbalanced,
        normalize=normalize,
        folds=folds,
        metric=metric,
        y_col=target_col,
        training_set=training_set,
        testing_set=testing_set,
        test_size=test_size,
    )
    return model


@main.command()
@click.option('-t', '--model-type', required=True, type=click.Choice(['regressor', 'classifier']),
              help='type of prediction model.')
@click.option('-i', '--input-file', required=True, help='testing dataset')
@click.option('-l', '--label-col', required=True, help='the target/phenotype/label column')
@click.option('-m', '--model-path', required=True, help='path to the trained model.')
@click.option('-s', '--samples-col', default='IID', help='the samples column.')
@click.option('-o', '--output-file', default=None, help='the path to output file.')
def test_model(
    *,
    model_path,
    input_file,
    model_type,
    label_col,
    samples_col,
    output_file,
):
    """
    Evaluate a machine learning model with a given dataset.

    :param model_path: the path to the ML model.
    :param input_file: the testing dataset.
    :param model_type: the type of model (classifier or regressor)
    :param label_col: the labels/target column.
    :param samples_col: the sample ids column.

    :return:
    """
    testing_df = model_testing(
        model_path=model_path,
        input_file=input_file,
        label_col=label_col,
        samples_col=samples_col,
        model_type=model_type,
    )
    testing_df.to_csv(output_file, sep='\t')
    return testing_df


@main.command()
@click.option('-p', '--plink', default='plink')
def get_prs(
    *,
    plink,
):
    """
    This command gets a pgs file (provided by the user or downloaded) then calculates the PRS scores for dataset.
    This command is interactive.

    :param plink: provide plink path if not default in environment.

    :return:
    """
    download = click.confirm('Do you want to download PGS file?')
    if download:
        pgs_id = click.prompt('Please input PGS ID', type=str)
        pgs_file = download_pgs(prs_id=pgs_id)
        p = subprocess.run(["zcat", pgs_file, "|", 'head', '-n', "15"], shell=True)
        if p.returncode != 0:
            click.echo('The PGS file could not be viewed using cmd, please view it manually.')
        click.echo('Please check the PGS file viewed and provide us with the needed columns.')
        id_col = click.prompt('Please provide the ID column number')
        allele = click.prompt('Please provide the effect allele column number')
        weight = click.prompt('Please provide the effect weight column number')
    else:
        pgs_file = click.prompt('Please provide path to PGS file', type=str)
        id_col = click.prompt('Please provide the ID column number')
        allele = click.prompt('Please provide the effect allele column number')
        weight = click.prompt('Please provide the effect weight column number')
    cols = ' '.join([str(id_col), str(allele), str(weight)])
    file_type = click.prompt('Do you have a VCF file or binary files?', type=click.Choice(['vcf', 'bfile']))
    input_file = click.prompt('Please provide the path to input file', type=str)
    confirm = click.confirm('Please be aware that variant ID in both input file and pgs file need to match.'
                            'Do you want to continue?')
    if confirm:
        output_file = click.prompt('Please provide an output file path', type=str)
        if file_type == 'vcf':
            p = subprocess.call(
                plink + " --vcf " + input_file + " --score " + pgs_file + " " + cols + " sum --out " + output_file,
                shell=True
            )
        else:
            p = subprocess.call(
                plink + " --bfile " + input_file + " --score " + pgs_file + " " + cols + " sum --out " + output_file,
                shell=True
            )
    else:
        click.echo('Ok. You still have the PGS file (if downloaded) but the scores were not calculated.')
    click.echo('Process is complete. Have a nice day!')


if __name__ == '__main__':
    main()
