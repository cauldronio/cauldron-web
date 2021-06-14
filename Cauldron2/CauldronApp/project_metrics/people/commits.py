import logging

from elasticsearch import ElasticsearchException
from elasticsearch_dsl import Search, Q

logger = logging.getLogger(__name__)


def contributors_and_affiliations(elastic, urls, from_date, to_date):
    """Get multiple metrics related with contributors"""
    s = Search(using=elastic, index='all') \
        .filter('range', grimoire_creation_date={'gte': from_date, "lte": to_date}) \
        .extra(size=0)

    if urls:
        s = s.query(Q('terms', origin=urls))

    s.aggs.bucket('authors', 'terms', field='author_name', size=10000, order={'_count': 'desc'}) \
          .bucket('authors_uuids', 'terms', field='author_uuid', size=10000, order={'_count': 'desc'}) \
          .bucket('authors_orgs', 'terms', field='author_org_name', size=5, order={'_count': 'desc'}) \
          .metric('last_contribution', 'max', field='grimoire_creation_date') \
          .metric('first_contribution', 'min', field='grimoire_creation_date')

    try:
        response = s.execute()
    except ElasticsearchException as e:
        logger.warning(e)
        response = None

    if response is not None and response.success():

        authors = []
        for author in response.aggregations.authors:
            for author_uuid in author.authors_uuids:
                for author_org in author_uuid.authors_orgs:
                    authors.append({"name": author.key,
                                    "author_uuid": author_uuid.key,
                                    "affiliation": author_org.key,
                                    "count": author_org.doc_count,
                                    "last_contribution": author_org.last_contribution.value,
                                    "first_contribution": author_org.first_contribution.value})

        return authors
    else:
        return None
