import time
import config as config
import pandas as pd
import json
from .apis.generic import Generic
from os.path import exists
from analysis import util
import logging


api_access = config.api_access_core
api_url = 'https://api.core.ac.uk/v3/search/works'
start = 0
max_papers = 1000
client_fields = {'title': 'title', 'abstract': 'abstract'}
database = 'core'
f = 'utf-8'
client = Generic()
waiting_time = 5
max_retries = 3
file_handler = ''
logger = logging.getLogger('logger')


def get_papers(query, synonyms, fields, types, dates, start_date, end_date, folder_name, search_date):
    global logger
    logger = logging.getLogger('logger')
    global file_handler
    file_handler = logger.handlers[1].baseFilename
    query_name = list(query.keys())[0]
    query_value = query[query_name]
    file_name = './papers/' + folder_name + '/' + str(search_date).replace('-', '_') + '/raw_papers/' \
                + query_name.lower().replace(' ', '_') + '_' + database + '.csv'
    if not exists(file_name):
        c_fields = []
        for field in fields:
            if field in client_fields:
                c_fields.append(client_fields[field])
        parameters = {'query': query_value, 'synonyms': synonyms, 'fields': c_fields, 'types': types}
        papers = request_papers(query, parameters, dates, start_date, end_date)
        papers = filter_papers(papers)
        papers = clean_papers(papers)
        if len(papers) > 0:
            util.save(file_name, papers, f)
        logger.info("Retrieved papers after filters and cleaning: " + str(len(papers)))
    else:
        logger.info("File already exists.")


def request_papers(query, parameters, dates, start_date, end_date):
    logger.info("Retrieving papers. It might take a while...")
    papers = pd.DataFrame()
    request = create_request(parameters, dates, start_date, end_date)
    raw_papers = client.request(api_url, 'post', request, api_access)
    expected_papers = get_expected_papers(raw_papers, request)
    times = int(expected_papers / max_papers) - 1
    mod = int(expected_papers) % max_papers
    if mod > 0:
        times = times + 1
    for t in range(0, times + 1):
        time.sleep(waiting_time)
        global start
        start = t * max_papers
        request = create_request(parameters, dates, start_date, end_date)
        raw_papers = client.request(api_url, 'post', request, api_access)
        # if there is an exception from the API, retry request
        retry = 0
        while isinstance(raw_papers, dict) and retry < max_retries:
            time.sleep(waiting_time)
            retry = retry + 1
            raw_papers = client.request(api_url, 'post', request, api_access)
        if not isinstance(raw_papers, dict):
            papers_request = process_raw_papers(query, raw_papers)
            if len(papers) == 0:
                papers = papers_request
            else:
                papers = papers.append(papers_request)
        else:
            logger.info("Error when requesting the API. Skipping to next request. Please see the log file for details: "
                        + file_handler)
            logger.debug("Error when requesting the API: " + raw_papers['exception'])
            logger.debug("Request: " + request)
    return papers


def create_request(parameters, dates, start_date, end_date):
    req = {}
    start_year = start_date.year
    end_year = end_date.year
    query = client.core_query(parameters)
    if dates:
        query = '(yearPublished>=' + str(start_year) + ' AND yearPublished<=' + str(end_year) + ') AND ' + query
    req['q'] = query
    req['scroll'] = "true"
    req['limit'] = max_papers
    req['offset'] = start
    return req


def get_expected_papers(raw_papers, request):
    total = 0
    try:
        raw_json = json.loads(raw_papers.content)
        total = raw_json['totalHits']
    except:
        logger.info("Error when requesting the API. Skipping to next request. Please see the log file for details: "
                    + file_handler)
        logger.debug("Error when requesting the API: " + raw_papers['exception'])
        logger.debug("Request: " + request)
    return total


def process_raw_papers(query, raw_papers):
    query_name = list(query.keys())[0]
    query_value = query[query_name]
    papers_request = pd.DataFrame()
    if not isinstance(raw_papers, dict):
        try:
            raw_json = json.loads(raw_papers.content)
            total = raw_json['totalHits']
            if total is not None and raw_json['results'] is not None:
                papers_request = pd.json_normalize(raw_json['results'])
                papers_request.loc[:, 'database'] = database
                papers_request.loc[:, 'query_name'] = query_name
                papers_request.loc[:, 'query_value'] = query_value.replace('&', 'AND').replace('Â¦', 'OR')
                if 'downloadUrl' not in papers_request:
                    papers_request[:, 'downloadUrl'] = ''
        except Exception as ex:
            logger.info("Error when requesting the API. Skipping to next request. Please see the log file for details: "
                        + file_handler)
            logger.debug("Error when processing raw papers: " + str(ex))
            papers_request = pd.DataFrame()

    return papers_request


def filter_papers(papers):
    if len(papers) > 0:
        papers = papers.drop_duplicates(subset=['title'])
    return papers


def clean_papers(papers):
    if len(papers) > 0:
        papers = papers.drop(columns=['acceptedDate', 'createdDate', 'arxivId', 'authors', 'citationCount',
                                      'contributors', 'outputs', 'createDate', 'dataProviders', 'depositedDate',
                                      'documentType', 'identifiers', 'fieldOfStudy', 'fullText', 'identifiers',
                                      'relations', 'magId', 'oaiIds', 'pubmedId', 'links', 'references',
                                      'sourceFulltextUrls', 'updatedDate', 'yearPublished', 'language.code',
                                      'language.id', 'language.name'], errors='ignore')
        papers.replace('', float("NaN"), inplace=True)
        papers.dropna(how='all', axis=1, inplace=True)
    return papers