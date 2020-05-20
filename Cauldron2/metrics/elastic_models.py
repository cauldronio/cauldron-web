from elasticsearch_dsl import Document, Date, Integer


class DailyMetrics(Document):
    date = Date()
    created_users = Integer()
    logged_users = Integer()
    created_projects = Integer()
    completed_tasks = Integer()

    class Index:
        name = 'cauldron_daily_metrics'


class MonthlyMetrics(Document):
    date = Date()
    created_users = Integer()
    logged_users = Integer()
    created_projects = Integer()
    completed_tasks = Integer()

    class Index:
        name = 'cauldron_monthly_metrics'
