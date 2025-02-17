import json
import logging
import os
from datetime import datetime, timedelta

import boto3
from metric_helper import gen_detailed_by_interval, get_athena_query_result

ATHENA_QUERY_OUTPUT = "s3://" + os.environ['S3_BUCKET'] + "/athena_results/"
athena_client = boto3.client('athena')
dynamodb = boto3.resource('dynamodb', region_name=os.environ['REGION_NAME'])
DB_NAME = os.environ['GLUE_DATABASE_NAME']
DDB_TABLE_NAME = os.environ['DDB_TABLE_NAME']
GLUE_TABLE_NAME = os.environ['GLUE_TABLE_NAME']
USE_START_TIME = os.environ['USE_START_TIME']
Interval_Minutes = 24 * 60

log = logging.getLogger()
log.setLevel('INFO')


def lambda_handler(event, context):
    log.info('[lambda_handler] Start')
    log.info('[lambda_handler] Event ' + json.dumps(event))

    response = {
        "isBase64Encoded": "false",
        "headers": {
            "Content-Type": "application/json"
        }
    }
    event_time = event["time"]
    event_datetime = datetime.strptime(
        event_time, "%Y-%m-%dT%H:%M:%SZ") - timedelta(minutes=5)
    start_datetime = event_datetime - timedelta(minutes=Interval_Minutes)
    start_time = start_datetime.strftime("%Y-%m-%d 00:00:00")
    end_time =  start_datetime.strftime("%Y-%m-%d 23:59:59")
    metric = "topNUrlSize"

    try:
        gen_data = gen_detailed_by_interval(metric, start_time, end_time,
                                            athena_client, DB_NAME,
                                            GLUE_TABLE_NAME, ATHENA_QUERY_OUTPUT,
                                            interval_minutes=Interval_Minutes, use_start=USE_START_TIME)
        for queryItem in gen_data['Detail']:
            log.info(json.dumps(queryItem))
            log.info(queryItem['QueryId'])
            item_query_result = get_athena_query_result(
                athena_client, queryItem['QueryId'])

            log.info(json.dumps(item_query_result))
            topn_url_size_dict = {}
            result_rows = item_query_result['ResultSet']['Rows']
            for i in range(1, len(result_rows)):
                if result_rows[i]['Data'][0].get(
                        'VarCharValue') is not None:
                    topn_url_size_row = {}
                    topn_url_size_row['Path'] = result_rows[i]['Data'][1]['VarCharValue']
                    topn_url_size_row['Size'] = result_rows[i]['Data'][2]['VarCharValue']
                    domain = result_rows[i]['Data'][0]['VarCharValue']

                    if domain in topn_url_size_dict.keys():
                        topn_url_size_dict[domain].append(topn_url_size_row)
                    else:
                        item_query_value = []
                        item_query_value.append(topn_url_size_row)
                        topn_url_size_dict[domain] = item_query_value

            # Skip if no value
            if len(topn_url_size_dict) != 0:
                for status_code_key in topn_url_size_dict.keys():
                    table_item = {
                        'metricId': metric + '-' + status_code_key,
                        'timestamp': int(queryItem['Time']),
                        'metricData': topn_url_size_dict[status_code_key]
                    }
                    table = dynamodb.Table(DDB_TABLE_NAME)
                    ddb_response = table.put_item(Item=table_item)
                    log.info(json.dumps(table_item))
                    log.info(str(ddb_response))

    except Exception as error:
        log.error(str(error))

    log.info('[lambda_handler] End')
    return response
