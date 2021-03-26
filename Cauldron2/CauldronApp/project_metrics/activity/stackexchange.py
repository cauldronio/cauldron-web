import json
import logging

from bokeh.embed import json_item
from bokeh.models import ColumnDataSource, tools
from bokeh.palettes import Blues
from bokeh.plotting import figure

from elasticsearch import ElasticsearchException
from elasticsearch_dsl import Search, Q

from ..utils import configure_figure

logger = logging.getLogger(__name__)


def num_questions(elastic, urls, from_date, to_date):
    """Get number of questions in the specified range"""
    s = Search(using=elastic, index='stackexchange')\
        .filter('range', grimoire_creation_date={'gte': from_date, "lte": to_date}) \
        .query(Q('match', is_stackexchange_question='1')) \
        .query(Q('terms', tag=urls)) \
        .extra(size=0)
    s.aggs.bucket('questions', 'cardinality', field='question_id')

    try:
        response = s.execute()
    except ElasticsearchException as e:
        logger.warning(e)
        response = None

    if response is not None and response.success():
        return response.aggregations.questions.value or 0
    else:
        return 'X'


def num_answers(elastic, urls, from_date, to_date):
    """Get number of questions in the specified range"""
    s = Search(using=elastic, index='stackexchange')\
        .filter('range', grimoire_creation_date={'gte': from_date, "lte": to_date}) \
        .query(Q('match', is_stackexchange_answer='1')) \
        .query(Q('terms', tag=urls))
    s.aggs.bucket('answers', 'cardinality', field='answer_id')

    try:
        response = s.execute()
    except ElasticsearchException as e:
        logger.warning(e)
        response = None

    if response is not None and response.success():
        return response.aggregations.answers.value or 0
    else:
        return 'X'


def questions_answers_bokeh(elastic, urls, from_date, to_date):
    """Visualization of questions and answers in the specified time rage"""
    s = Search(using=elastic, index='stackexchange') \
        .query(Q('terms', tag=urls)) \
        .extra(size=0)
    s.aggs.bucket('range_questions', 'filter', Q('range', grimoire_creation_date={'gte': from_date, "lte": to_date}) &
                  Q('match', is_stackexchange_question='1')) \
        .bucket('questions', 'auto_date_histogram', field='grimoire_creation_date', buckets=40)
    s.aggs.bucket('range_answers', 'filter', Q('range', grimoire_creation_date={'gte': from_date, "lte": to_date}) &
                  Q('match', is_stackexchange_answer='1')) \
        .bucket('answers', 'auto_date_histogram', field='grimoire_creation_date', buckets=40)

    try:
        response = s.execute()
        question_buckets = response.aggregations.range_questions.questions.buckets
        answer_buckets = response.aggregations.range_answers.answers.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        question_buckets = []
        answer_buckets = []

    # Create the data structure
    data = {
        'timestamps_questions': [],
        'number_questions': [],
        'timestamps_answers': [],
        'number_answers': []
    }
    for citem in question_buckets:
        data['timestamps_questions'].append(citem.key)
        data['number_questions'].append(citem.doc_count)

    for oitem in answer_buckets:
        data['timestamps_answers'].append(oitem.key)
        data['number_answers'].append(oitem.doc_count)
    ds = ColumnDataSource(data)

    # Create the Bokeh visualization
    plot = figure(x_axis_type="datetime",
                  x_axis_label='Date',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')
    configure_figure(plot, '')
    plot.title.text = '# StackExchange Questions & Answers'

    plot.circle(x='timestamps_questions', y='number_questions',
                color=Blues[3][0],
                size=8,
                source=ds)

    plot.line(x='timestamps_questions', y='number_questions',
              name='number_questions',
              line_width=4,
              line_color=Blues[3][0],
              legend_label='# Questions',
              source=ds)

    plot.circle(x='timestamps_answers', y='number_answers',
                color=Blues[3][1],
                size=8,
                source=ds)

    plot.line(x='timestamps_answers', y='number_answers',
              name='number_answers',
              line_width=4,
              line_color=Blues[3][1],
              legend_label='# Answers',
              source=ds)

    plot.add_tools(tools.HoverTool(
        names=['number_questions'],
        tooltips=[
            ('Date', '@timestamps_questions{%F}'),
            ('# Questions', '@number_questions'),
            ('# Answers', '@number_answers'),
        ],
        formatters={
            '@timestamps_questions': 'datetime'
        },
        mode='vline',
        toggleable=False
    ))
    plot.legend.location = "top_left"

    return json.dumps(json_item(plot))
