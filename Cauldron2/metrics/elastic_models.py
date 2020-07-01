from elasticsearch_dsl import Document, Date, Integer, Float


class DailyMetrics(Document):
    date = Date()
    created_users = Integer()
    logged_users = Integer()
    created_projects = Integer()
    completed_tasks = Integer()
    projects_per_user = Float()
    activated_users = Integer()
    real_users = Integer()
    m2 = Integer()
    m3 = Integer()

    class Index:
        name = 'cauldron_daily_metrics'


class BiweeklyMetrics(Document):
    date = Date()
    created_users = Integer()
    logged_users = Integer()
    created_projects = Integer()
    completed_tasks = Integer()
    projects_per_user = Float()
    activated_users = Integer()
    real_users = Integer()
    m2 = Integer()
    m3 = Integer()

    class Index:
        name = 'cauldron_biweekly_metrics'


class MonthlyMetrics(Document):
    date = Date()
    created_users = Integer()
    logged_users = Integer()
    created_projects = Integer()
    completed_tasks = Integer()
    projects_per_user = Float()
    activated_users = Integer()
    real_users = Integer()
    m2 = Integer()
    m3 = Integer()

    class Index:
        name = 'cauldron_monthly_metrics'
