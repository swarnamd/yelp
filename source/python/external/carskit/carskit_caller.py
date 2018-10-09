import json
import os
import subprocess
import uuid

import time

import collections

import jprops
import pandas

from etl import ETLUtils
from utils.constants import Constants

JAVA_COMMAND = 'java'
# CARSKIT_JAR = 'CARSKit-v0.3.0.jar'
CARSKIT_JAR = 'CARSKit.jar'
CARSKIT_ORIGINAL_CONF_FILE = Constants.CARSKIT_FOLDER + 'setting.conf'
OUTPUT_FOLDER = Constants.DATASET_FOLDER + 'carskit_results/'


def run_carskit(fold):

    jar_file = Constants.CARSKIT_FOLDER + CARSKIT_JAR
    CARSKIT_CONF_FOLD_FOLDER = Constants.RIVAL_RATINGS_FOLD_FOLDER + 'carskit/'
    CARSKIT_MODIFIED_CONF_FILE = CARSKIT_CONF_FOLD_FOLDER + '%s.conf'

    command = [
        JAVA_COMMAND,
        '-jar',
        jar_file,
        '-c',
        CARSKIT_MODIFIED_CONF_FILE % (fold, Constants.CARSKIT_RECOMMENDERS),
    ]

    print(" ".join(command))

    unique_id = uuid.uuid4().hex
    log_file_name = Constants.GENERATED_FOLDER + Constants.ITEM_TYPE + '_' + \
        Constants.TOPIC_MODEL_TARGET_REVIEWS + '_parse_directory_' +\
        unique_id + '.log'

    log_file = open(log_file_name, 'w')
    p = subprocess.Popen(
        command, stdout=log_file, cwd=OUTPUT_FOLDER)
    p.wait()


def result_to_dict(result):
    """
    Takes one line from the results file generated by CARSKit and transforms it
    into a dictionary in the form of {'metric': value}. For instance a
    dictionary could be
    {'algorithm': 'svd', 'RMSE': 1.24, 'MAE': 0.9, 'num_factors': 10}

    :param result: the resulting dictionary with the information about the
    performance of the algorithm and the hyperparameters used
    """
    split_metrics = [metric.strip() for metric in result.split(',')]
    print(split_metrics)

    results_map = {}

    # Results from position 0 tell the algorithm
    algorithm = 'ck_' + split_metrics[0].split(' ')[-1].lower()
    results_map['ck_algorithm'] = algorithm

    unknown_count = 1

    for metric in split_metrics[1:-2]:
        metric_info = metric.split(': ')

        if len(metric_info) == 1:
            results_map[algorithm + str(unknown_count)] = metric_info[0]
            unknown_count += 1
        elif len(metric_info) == 2:
            results_map['ck_' + metric_info[0].lower()] = metric_info[1]
        else:
            print(metric_info)
            raise ValueError('Unrecognized results format')

    # Results from the last two positions tell the time
    results_map['ck_train_time'] = split_metrics[-2].split(': ')[1]
    results_map['ck_test_time'] = split_metrics[-1]

    return results_map


def save_results(results):

    # Take the results given by the run_carskit function and extend them with
    # the Constants.get_properties() dictionary, then save them to a CSV file

    """

    :type results: list[dict]
    :param results:
    """
    properties = Constants.get_properties_copy()

    json_file = Constants.generate_file_name(
        'carskit_results', 'json', OUTPUT_FOLDER, None, None, False)

    for result in results:
        result.update(properties)
        write_results_to_json(json_file, result)


def export_results(fold):

    recommender = Constants.CARSKIT_RECOMMENDERS
    ratings_fold_folder = Constants.RIVAL_RATINGS_FOLD_FOLDER % fold
    prediction_type_map = {
        'user_test': 'rating',
        'test_items': 'rating',
        'rel_plus_n': 'ranking'
    }
    prediction_type = prediction_type_map[Constants.RIVAL_EVALUATION_STRATEGY]
    # ratings_file = ratings_fold_folder + 'UserSplitting-BiasedMF-rating-predictions.txt'
    ratings_file = ratings_fold_folder + recommender + '-rating-predictions.txt'
    results_file = ratings_fold_folder + 'carskit_' + recommender +\
                   '_results_' + prediction_type + '.txt'

    records = ETLUtils.load_csv_file(ratings_file, '\t')
    predictions = [record['prediction'] for record in records]

    with open(results_file, 'w') as f:
        for prediction in predictions:
            f.write("%s\n" % prediction)


def full_cycle(fold):
    # file_name = 'results_all_2016.txt'
    # carskit_results_file = OUTPUT_FOLDER + file_name

    modify_properties_file(fold)
    run_carskit(fold)
    export_results(fold)

    # with open(carskit_results_file) as results_file:
    #     results = results_file.readlines()

    # results_list = [result_to_dict(result) for result in results]
    # save_results(results_list)

    # We remove the carskit results file because if not then we would be saving
    # the results from previous runs and we would have them duplicated
    # os.remove(carskit_results_file)


def modify_properties_file(fold):
    with open(CARSKIT_ORIGINAL_CONF_FILE) as read_file:
        properties = jprops.load_properties(read_file, collections.OrderedDict)

    CARSKIT_CONF_FOLD_FOLDER = Constants.RIVAL_RATINGS_FOLD_FOLDER + 'carskit/'
    CARSKIT_MODIFIED_CONF_FILE = CARSKIT_CONF_FOLD_FOLDER + '%s.conf'
    recommender = Constants.CARSKIT_RECOMMENDERS
    carskit_conf_fold_folder = CARSKIT_CONF_FOLD_FOLDER % fold
    ratings_fold_folder = Constants.RIVAL_RATINGS_FOLD_FOLDER % fold
    prediction_type_map = {
        'user_test': 'rating',
        'test_items': 'rating',
        'rel_plus_n': 'ranking'
    }
    prediction_type = prediction_type_map[Constants.RIVAL_EVALUATION_STRATEGY]

    if not os.path.exists(carskit_conf_fold_folder):
        os.makedirs(carskit_conf_fold_folder)

    modified_file = CARSKIT_MODIFIED_CONF_FILE % (fold, recommender)
    properties['recommender'] = recommender
    train_file = ratings_fold_folder + 'carskit_train.csv'
    test_file = \
        ratings_fold_folder + 'carskit_predictions_%s.csv' % (prediction_type)
    properties['dataset.ratings.lins'] = train_file
    properties['evaluation.setup'] = \
        'test-set -f %s --rand-seed 1 --test-view all' % test_file
    properties['item.ranking'] = 'off'

    properties['output.setup'] =\
        '-folder %s -verbose on, off --to-file %s%s_summary.txt' % (
            ratings_fold_folder, ratings_fold_folder, recommender)

    params = process_carskit_parameters(Constants.CARSKIT_PARAMETERS)

    for key, value in params.items():
        properties[key] = value

    with open(modified_file, 'w') as write_file:
        jprops.store_properties(write_file, properties)


def process_carskit_parameters(carskit_parameters):

    if carskit_parameters is None:
        return None

    print(carskit_parameters)

    param_map = dict(item.split("=") for item in carskit_parameters.split(","))
    return param_map


def write_results_to_json(json_file, results):
    if not os.path.exists(json_file):
        with open(json_file, 'w') as f:
            json.dump(results, f)
            f.write('\n')
    else:
        with open(json_file, 'a') as f:
            json.dump(results, f)
            f.write('\n')


def analyze_results():
    json_file = Constants.generate_file_name(
        'carskit_results', 'json', OUTPUT_FOLDER, None, None, False)
    records = ETLUtils.load_json_file(json_file)

    data_frame = pandas.DataFrame(records)
    print(sorted(list(data_frame.columns.values)))
    cols = [
        'ck_rec10', 'ck_pre10', 'ck_algorithm', 'carskit_nominal_format',
        'topic_model_num_topics', 'topic_model_normalize']
    data_frame = data_frame[cols]
    data_frame = data_frame.sort_values(['ck_rec10'])
    print(data_frame)

    data_frame.to_csv('/Users/fpena/tmp/' + Constants.ITEM_TYPE + '_carskit.csv')


def old_main():

    # modify_properties_file()
    # run_carskit()

    # baseline-Avg recommender: GlobalAvg, UserAvg, ItemAvg, UserItemAvg
    # baseline-Context average recommender: ContextAvg, ItemContextAvg, UserContextAvg
    # baseline-CF recommender: ItemKNN, UserKNN, SlopeOne, PMF, BPMF, BiasedMF, NMF, SVD++
    # baseline-Top-N ranking recommender: SLIM, BPR, RankALS, RankSGD, LRMF
    # CARS - splitting approaches: UserSplitting, ItemSplitting, UISplitting; algorithm options: e.g., usersplitting -traditional biasedmf -minlenu 2 -minleni 2
    # CARS - filtering approaches: SPF, DCR, DCW
    # CARS - independent models: CPTF
    # CARS - dependent-dev models: CAMF_CI, CAMF_CU, CAMF_C, CAMF_CUCI, CSLIM_C, CSLIM_CI, CSLIM_CU, CSLIM_CUCI, GCSLIM_CC
    # CARS - dependent-sim models: CAMF_ICS, CAMF_LCS, CAMF_LCS, CSLIM_ICS, CSLIM_LCS, CSLIM_MCS, GCSLIM_ICS, GCSLIM_LCS, GCSLIM_MCS

    if Constants.CARSKIT_ITEM_RANKING:
        all_recommenders = [
            'globalavg', 'useravg', 'itemavg', 'useritemavg',
            'slopeone', 'pmf', 'bpmf', 'biasedmf', 'nmf',
            'slim',  # 'bpr',  # 'rankals', 'ranksgd',
            'bpr',
            'lrmf',
            'camf_ci', 'camf_cu',  # 'camf_c',
            'camf_cuci', 'cslim_c', 'cslim_ci',
            'cslim_cu',  # 'cslim_cuci',
            # 'camf_ics',
            ##'camf_lcs', 'camf_mcs', 'cslim_ics', 'cslim_lcs',
            ##'cslim_mcs', 'gcslim_ics'
        ]
    else:
        all_recommenders = [
            'globalavg', 'useravg', 'itemavg', 'useritemavg',
            'slopeone', 'pmf', 'biasedmf', 'nmf',
            'camf_ci', 'camf_cu',  # 'camf_c',
            'camf_cuci',
            'bpmf',
        ]

    slow_recommenders = [
        # 'contextavg', 'itemcontextavg', 'usercontextavg',  # broken without context
        ## 'itemknn',
        ## 'userknn',
        ## 'cptf',
        ## 'gcslim_cc',
        ## 'gcslim_lcs',
        ## 'gcslim_mcs',
        ## 'fm'
    ]

    rating_recommenders = [
        'globalavg', 'useravg', 'itemavg', 'useritemavg',
        # 'contextavg', 'itemcontextavg', 'usercontextavg',
        'itemknn', 'userknn', 'slopeone', 'pmf', 'biasedmf', 'nmf',
        'cptf',
        'camf_ci', 'camf_cu', 'camf_c', 'camf_cuci',
        'camf_ics', 'camf_lcs', 'camf_mcs',
        'fm'
    ]

    rank_recommenders = [
        'globalavg', 'useravg', 'itemavg', 'useritemavg',
        # 'contextavg', 'itemcontextavg', 'usercontextavg',
        'itemknn', 'userknn', 'slopeone', 'pmf', 'bpmf', 'biasedmf', 'nmf',
        'slim', 'bpr',  # 'rankals', 'ranksgd',
        'lrmf',
        'cptf',
        'camf_ci', 'camf_cu', 'camf_c', 'camf_cuci', 'cslim_c', 'cslim_ci',
        'cslim_cu',  # 'cslim_cuci',
        'gcslim_cc',
        # 'camf_ics',
        'camf_lcs', 'camf_mcs', 'cslim_ics', 'cslim_lcs',
        'cslim_mcs', 'gcslim_ics', 'gcslim_lcs', 'gcslim_mcs',
        'fm'
    ]

    rank_only_recommenders = [
        'slim', 'bpr',  # 'rankals', 'ranksgd',
        'lrmf',
        'cslim_c', 'cslim_ci',
        'cslim_cu',  # 'cslim_cuci',
        'gcslim_cc',
        'cslim_ics', 'cslim_lcs',
        'cslim_mcs', 'gcslim_ics', 'gcslim_lcs', 'gcslim_mcs'
    ]

    # recommenders = all_recommenders
    recommenders = ['CAMF_CU']

    print('num recommenders: %d' % len(recommenders))
    index = 1

    for recommender in recommenders:
        print('cycle %d/%d' % (index, len(recommenders)))
        print('Recommender: %s' % recommender)
        Constants.update_properties({'carskit_recommenders': recommender})
        index += 1

        cycle_start = time.time()
        num_folds = Constants.CROSS_VALIDATION_NUM_FOLDS
        for fold in range(num_folds):
            # modify_properties_file(fold)
            full_cycle(fold)
        cycle_end = time.time()
        cycle_time = cycle_end - cycle_start
        print("Cycle time = %f seconds" % cycle_time)
    # analyze_results()


def main():

    cycle_start = time.time()
    num_folds = Constants.CROSS_VALIDATION_NUM_FOLDS
    for fold in range(num_folds):
        full_cycle(fold)
    cycle_end = time.time()
    cycle_time = cycle_end - cycle_start
    print("Cycle time = %f seconds" % cycle_time)

    # params = 'num.factors=10;num.max.iter=100;num.neighbors=5;DCW=-wt 0.9 -wd 0.4 -p 5 -lp 2.05 -lg 2.05 -th 0.8'
    # print(process_carskit_parameters(params))


# start = time.time()
# main()
# end = time.time()
# total_time = end - start
# print("Total time = %f seconds" % total_time)
