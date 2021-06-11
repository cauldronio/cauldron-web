import json
import logging
from datetime import timedelta

from bokeh.embed import json_item
from bokeh.models import ColumnDataSource, tools, Range1d
from bokeh.palettes import Blues
from bokeh.plotting import figure

from elasticsearch import ElasticsearchException
from elasticsearch_dsl import Search, Q

from ..utils import configure_figure, get_interval

logger = logging.getLogger(__name__)


def questions(elastic, urls, from_date, to_date):
    """Gives the number of StackExchange questions in a period"""
    s = Search(using=elastic, index='stackexchange') \
        .filter('range', grimoire_creation_date={'gte': from_date, "lte": to_date}) \
        .filter(Q('match', is_stackexchange_question='1')) \
        .filter(Q('terms', tag=urls)) \
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
        return '?'


def answers(elastic, urls, from_date, to_date):
    """Gives the number of StackExchange answers in a period"""
    s = Search(using=elastic, index='stackexchange') \
        .filter('range', grimoire_creation_date={'gte': from_date, "lte": to_date}) \
        .filter(Q('match', is_stackexchange_answer='1')) \
        .filter(Q('terms', tag=urls)) \
        .extra(size=0)
    s.aggs.bucket('answers', 'cardinality', field='answer_id')

    try:
        response = s.execute()
    except ElasticsearchException as e:
        logger.warning(e)
        response = None

    if response is not None and response.success():
        return response.aggregations.answers.value or 0
    else:
        return '?'


def questions_over_time(elastic, urls, from_date, to_date, interval):
    """Gives the number of StackExchange questions grouped by date"""
    s = Search(using=elastic, index='stackexchange') \
        .filter('range', grimoire_creation_date={'gte': from_date, "lte": to_date}) \
        .filter(Q('match', is_stackexchange_question='1')) \
        .filter(Q('terms', tag=urls)) \
        .extra(size=0)
    s.aggs.bucket('dates', 'date_histogram', field='grimoire_creation_date', calendar_interval=interval) \
          .bucket('questions', 'cardinality', field='question_id')

    try:
        response = s.execute()
        dates_buckets = response.aggregations.dates.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        dates_buckets = []

    timestamps, questions = [], []
    for period in dates_buckets:
        timestamps.append(period.key)
        questions.append(period.questions.value)

    return timestamps, questions


def answers_over_time(elastic, urls, from_date, to_date, interval):
    """Gives the number of StackExchange answers grouped by date"""
    s = Search(using=elastic, index='stackexchange') \
        .filter('range', grimoire_creation_date={'gte': from_date, "lte": to_date}) \
        .filter(Q('match', is_stackexchange_answer='1')) \
        .filter(Q('terms', tag=urls)) \
        .extra(size=0)
    s.aggs.bucket('dates', 'date_histogram', field='grimoire_creation_date', calendar_interval=interval) \
          .bucket('answers', 'cardinality', field='answer_id')

    try:
        response = s.execute()
        dates_buckets = response.aggregations.dates.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        dates_buckets = []

    timestamps, answers = [], []
    for period in dates_buckets:
        timestamps.append(period.key)
        answers.append(period.answers.value)

    return timestamps, answers


def questions_bokeh(elastic, urls, from_date, to_date):
    """Get evolution of StackExchange questions (line chart)"""
    interval_name, interval_elastic, _ = get_interval(from_date, to_date)

    timestamps, questions = questions_over_time(elastic, urls, from_date, to_date, interval_elastic)

    plot = figure(x_axis_type="datetime",
                  x_axis_label='Time',
                  y_axis_label='# Questions',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')
    plot.title.text = '# Questions'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/activity/questions-chart.md')
    if len(timestamps) > 0:
        plot.x_range = Range1d(from_date - timedelta(days=1), to_date + timedelta(days=1))

    source = ColumnDataSource(data=dict(
        questions=questions,
        timestamps=timestamps
    ))

    plot.circle(x='timestamps', y='questions',
                color=Blues[3][0],
                size=8,
                source=source)

    plot.line(x='timestamps', y='questions',
              line_width=4,
              line_color=Blues[3][0],
              source=source)

    plot.add_tools(tools.HoverTool(
        tooltips=[
            (interval_name, '@timestamps{%F}'),
            ('questions', '@questions')
        ],
        formatters={
            '@timestamps': 'datetime'
        },
        mode='vline',
        toggleable=False
    ))

    return json.dumps(json_item(plot))


def answers_bokeh(elastic, urls, from_date, to_date):
    """Get evolution of StackExchange answers (line chart)"""
    interval_name, interval_elastic, _ = get_interval(from_date, to_date)

    timestamps, answers = answers_over_time(elastic, urls, from_date, to_date, interval_elastic)

    plot = figure(x_axis_type="datetime",
                  x_axis_label='Time',
                  y_axis_label='# Answers',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')
    plot.title.text = '# Answers'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/activity/answers-chart.md')
    if len(timestamps) > 0:
        plot.x_range = Range1d(from_date - timedelta(days=1), to_date + timedelta(days=1))

    source = ColumnDataSource(data=dict(
        answers=answers,
        timestamps=timestamps
    ))

    plot.circle(x='timestamps', y='answers',
                color=Blues[3][0],
                size=8,
                source=source)

    plot.line(x='timestamps', y='answers',
              line_width=4,
              line_color=Blues[3][0],
              source=source)

    plot.add_tools(tools.HoverTool(
        tooltips=[
            (interval_name, '@timestamps{%F}'),
            ('answers', '@answers')
        ],
        formatters={
            '@timestamps': 'datetime'
        },
        mode='vline',
        toggleable=False
    ))

    return json.dumps(json_item(plot))


def questions_answers_bokeh(elastic, urls, from_date, to_date):
    """Visualization of questions and answers in the specified time rage"""
    s = Search(using=elastic, index='stackexchange') \
        .filter(Q('terms', tag=urls)) \
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
