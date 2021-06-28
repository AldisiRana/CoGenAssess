# -*- coding: utf-8 -*-
import os
import random
import subprocess

import joblib
import numpy as np
import pandas as pd
import pycaret.classification as cl
import pycaret.regression as pyreg
import sklearn.metrics as metrics
from pycaret.utils import check_metric
from statsmodels.stats.multitest import multipletests

from .helpers import run_mannwhitneyu, run_ttest, get_pvals_logit, get_pvals_linear, generate_scatterplot, \
    generate_confusion_matrix, write_output

PATH = os.path.abspath(os.path.join((__file__), os.pardir, os.pardir, os.pardir))
BETAREG_SHELL = os.path.join(PATH, 'scripts', 'betareg_shell.R')
association_functions = {
    'mannwhitneyu': run_mannwhitneyu,
    'ttest_ind': run_ttest,
    'logit': get_pvals_logit,
    'linear': get_pvals_linear,
}


def find_pvalue(
    *,
    scores_file,
    info_file,
    output_file,
    genes=None,
    cases_column,
    samples_column,
    test='mannwhitneyu',
    adj_pval,
    covariates=None,
    cases=None,
    controls=None,
    processes=1,
):
    """
    Calculate the significance of a gene in a population using Mann-Whitney-U test.
    \f

    :param test: the type of statistical test to use, choices are: t-test, mannwhitenyu, GLM, logit.
    :param scores_file: dataframe containing the scores of genes across samples.
    :param info_file: a file containing the information of the sample.
    :param output_file: a path to save the output file.
    :param genes: a list of the genes to calculate the significance. if None will calculate for all genes.
    :param cases_column: the name of the column containing cases and controls information.
    :param samples_column: the name of the column contining samples IDs.
    :param adj_pval: the method for pvalue adjustment.
    :param controls: the name of the controls category.
    :param cases:  the name of the cases category.
    :param covariates: the covariates of the phenotype.
    :param processes: number of processes working in parallel.

    :return: dataframe with genes and their p_values
    """
    scores_df = pd.read_csv(scores_file, sep=r'\s+', index_col=samples_column)
    scores_df.replace([np.inf, -np.inf], 0, inplace=True)
    scores_df.fillna(0, inplace=True)
    scores_df = scores_df.loc[:, scores_df.var() != 0.0].reset_index()
    genotype_df = pd.read_csv(info_file, sep='\t')
    genotype_df.dropna(subset=[cases_column], inplace=True)
    merged_df = genotype_df.merge(scores_df, how='inner', on=samples_column)
    merged_df.replace([np.inf, -np.inf], 0, inplace=True)
    merged_df.fillna(0, inplace=True)
    if genes is None:
        genes = scores_df.columns.tolist()[1:]
    del scores_df
    if covariates:
        covariates = covariates.split(',')
    args = {
        'processes': processes, 'cases': cases, 'controls': controls, 'covariates': covariates,
    }
    p_values_df = association_functions.get(test)(df=merged_df, genes=genes, cases_column=cases_column, **args)
    if adj_pval:
        adjusted = multipletests(list(p_values_df['p_value']), method=adj_pval)
        p_values_df[adj_pval + '_adj_pval'] = list(adjusted)[1]
    p_values_df.to_csv(output_file, sep='\t', index=False)
    return p_values_df


def betareg_pvalues(
    *,
    scores_file,
    pheno_file,
    samples_col,
    cases_col,
    output_path,
    covariates,
    processes
):
    """
    Calculate association significance between two groups using betareg.
    \f

    :param scores_file: the path to the scores file.
    :param pheno_file:  the path to the phenotypes and covariates file.
    :param samples_col: the name of the column containing the samples IDs.
    :param cases_col: the name of the column containing the case/controls.
    :param output_path: the path to the output file.
    :param covariates: the covariates used in calculations, written with no space and comma in between (e.g PC1,PC2)
    :param processes: number of processes to parallelize.

    :return:
    """
    p = subprocess.call(
        ["Rscript", BETAREG_SHELL,
         "-s", scores_file,
         "--phenofile", pheno_file,
         "--samplescol", samples_col,
         "--casescol", cases_col,
         "-o", output_path,
         "--covariates", covariates,
         "--processes", str(processes)]
    )


def create_prediction_model(
    *,
    model_name='final_model',
    model_type='regressor',
    y_col,
    imbalanced=True,
    normalize=True,
    folds=10,
    training_set,
    testing_set=pd.DataFrame(),
    test_size=0.25,
    metric=None,
):
    """
    Create a prediction model (classifier or regressor) using the provided dataset.
    \f

    :param model_name: the name of the prediction model.
    :param model_type: type of model (reg or classifier).
    :param y_col: the column containing the target (qualitative or quantitative).
    :param imbalanced: True means data is imbalanced.
    :param normalize: True if data needs normalization.
    :param folds: how many folds for cross-validation.
    :param training_set: the training set for the model.
    :param testing_set: if exists an extra evaluation step will be done using the testing set.
    :param test_size: the size to split the training/testing set.
    :param metric: the metric to evaluate the best model.
    :return: the metrics.
    """
    if model_type == 'regressor':
        if not metric:
            metric = 'RMSE'
        setup = pyreg.setup(target=y_col, data=training_set, normalize=normalize, train_size=1 - test_size, fold=folds,
                            silent=True, session_id=random.randint(1, 2147483647))
        best_model = pyreg.compare_models(sort=metric)
        pyreg.pull().to_csv(model_name + '_compare_models.tsv', sep='\t', index=False)
        reg_model = pyreg.create_model(best_model)
        reg_tuned_model = pyreg.tune_model(reg_model, optimize=metric)
        pyreg.pull().to_csv(model_name + '_tuned_model.tsv', sep='\t', index=False)
        final_model = pyreg.finalize_model(reg_tuned_model)
        pyreg.plot_model(final_model, save=True)
        pyreg.plot_model(final_model, plot='feature', save=True)
        pyreg.plot_model(final_model, plot='error', save=True)
        if len(testing_set.index) != 0:
            unseen_predictions = pyreg.predict_model(final_model, data=testing_set)
            r2 = check_metric(unseen_predictions[y_col], unseen_predictions.Label, 'R2')
            rmse = check_metric(unseen_predictions[y_col], unseen_predictions.Label, 'RMSE')
            textfile = open(model_name + "_report.txt", "w")
            textfile.write('Testing model report: \n')
            textfile.write('R^2 = ' + str(r2) + '\n')
            textfile.write('RMSE = ' + str(rmse) + '\n')
            textfile.close()
            unseen_predictions.to_csv(model_name + '_external_testing_results.tsv', sep='\t', index=False)
        pyreg.save_model(final_model, model_name)
    elif model_type == 'classifier':
        if not metric:
            metric = 'AUC'
        setup = cl.setup(target=y_col, fix_imbalance=imbalanced, data=training_set, train_size=1 - test_size,
                         silent=True, fold=folds, session_id=random.randint(1, 2147483647))
        best_model = cl.compare_models(sort=metric)
        cl.pull().to_csv(model_name + '_compare_models.tsv', sep='\t', index=False)
        cl_model = cl.create_model(best_model)
        cl_tuned_model = cl.tune_model(cl_model, optimize=metric)
        cl.pull().to_csv(model_name + '_tuned_model.tsv', sep='\t', index=False)
        final_model = cl.finalize_model(cl_tuned_model)
        cl.plot_model(final_model, plot='pr', save=True)
        cl.plot_model(final_model, plot='confusion_matrix', save=True)
        cl.plot_model(final_model, plot='feature', save=True)
        if len(testing_set.index) != 0:
            unseen_predictions = cl.predict_model(final_model, data=testing_set)
            auc = check_metric(unseen_predictions[y_col], unseen_predictions.Label, 'AUC')
            accuracy = check_metric(unseen_predictions[y_col], unseen_predictions.Label, 'Accuracy')
            textfile = open(model_name + "_report.txt", "w")
            textfile.write('Testing model report: \n')
            textfile.write('AUC: ' + str(auc) + '\n')
            textfile.write('Accuracy: ' + str(accuracy) + '\n')
            textfile.close()
            unseen_predictions.to_csv(model_name + '_external_testing_results.tsv', sep='\t', index=False)
        cl.save_model(final_model, model_name)
    else:
        return Exception('Model requested is not available. Please choose regressor or classifier.')
    return final_model


def model_testing(
    *,
    model_path,
    input_file,
    samples_col,
    label_col,
    model_type
):
    """
    Load a prediction model and use it to predict label values in a dataset.
    \f

    :param model_path: the path to saved model.
    :param input_file: the file with features and label.
    :param samples_col: the name of samples column.
    :param label_col: the name of the target column.
    :param model_type: regressor or classifier

    :return: a dataframe with prediction values.
    """
    model = joblib.load(model_path)
    testing_df = pd.read_csv(input_file, sep='\t', index_col=samples_col)
    x_set = testing_df.drop(columns=label_col)
    if model_type == 'classifier':
        unseen_predictions = cl.predict_model(model, data=x_set)
        report = metrics.classification_report(testing_df[label_col], unseen_predictions.Label)
        acc = metrics.accuracy_score(testing_df[label_col], unseen_predictions.Label)
        auc = metrics.auc(testing_df[label_col], unseen_predictions.Label)
        plot = generate_confusion_matrix(x_set=x_set, y_set=testing_df[label_col], output=input_file.split('.')[0])
        input_list = [
            'Testing model report: \n', report + '\n', 'AUC = ' + str(auc) + '\n', 'Accuracy = ' + str(acc) + '\n'
        ]
        write_output(input_list=input_list, output=input_file.split('.')[0] + "_report.txt")
    else:
        unseen_predictions = pyreg.predict_model(model, data=x_set)
        r2 = metrics.r2_score(testing_df[label_col], unseen_predictions.Label)
        rmse = metrics.mean_squared_error(testing_df[label_col], unseen_predictions.Label, squared=False)
        plot = generate_scatterplot(
            x_axis=unseen_predictions.Label, y_axis=testing_df[label_col], output=input_file.split('.')[0])
        input_list = ['Testing model report: \n', 'R^2 = ' + str(r2) + '\n', 'RMSE = ' + str(rmse) + '\n']
        write_output(input_list=input_list, output=input_file.split('.')[0] + "_report.txt")
    prediction_df = unseen_predictions[['Label']]
    return prediction_df
