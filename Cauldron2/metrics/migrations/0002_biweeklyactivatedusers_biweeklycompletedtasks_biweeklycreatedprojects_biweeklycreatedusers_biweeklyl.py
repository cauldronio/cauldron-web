# Generated by Django 3.0.7 on 2020-07-01 15:41

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('metrics', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='BiweeklyActivatedUsers',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(unique=True)),
                ('total', models.IntegerField()),
            ],
            options={
                'verbose_name_plural': 'Biweekly Activated Users',
            },
        ),
        migrations.CreateModel(
            name='BiweeklyCompletedTasks',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(unique=True)),
                ('total', models.IntegerField()),
            ],
            options={
                'verbose_name_plural': 'Biweekly Completed Tasks',
            },
        ),
        migrations.CreateModel(
            name='BiweeklyCreatedProjects',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(unique=True)),
                ('total', models.IntegerField()),
            ],
            options={
                'verbose_name_plural': 'Biweekly Created Projects',
            },
        ),
        migrations.CreateModel(
            name='BiweeklyCreatedUsers',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(unique=True)),
                ('total', models.IntegerField()),
            ],
            options={
                'verbose_name_plural': 'Biweekly Created Users',
            },
        ),
        migrations.CreateModel(
            name='BiweeklyLoggedUsers',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(unique=True)),
                ('total', models.IntegerField()),
            ],
            options={
                'verbose_name_plural': 'Biweekly Logged Users',
            },
        ),
        migrations.CreateModel(
            name='BiweeklyM2',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(unique=True)),
                ('total', models.IntegerField()),
            ],
            options={
                'verbose_name_plural': 'Biweekly M2',
            },
        ),
        migrations.CreateModel(
            name='BiweeklyM3',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(unique=True)),
                ('total', models.IntegerField()),
            ],
            options={
                'verbose_name_plural': 'Biweekly M3',
            },
        ),
        migrations.CreateModel(
            name='BiweeklyProjectsPerUser',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(unique=True)),
                ('total', models.IntegerField()),
            ],
            options={
                'verbose_name_plural': 'Biweekly Projects per User',
            },
        ),
        migrations.CreateModel(
            name='BiweeklyRealUsers',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(unique=True)),
                ('total', models.IntegerField()),
            ],
            options={
                'verbose_name_plural': 'Biweekly Real Users',
            },
        ),
        migrations.CreateModel(
            name='DailyActivatedUsers',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(unique=True)),
                ('total', models.IntegerField()),
            ],
            options={
                'verbose_name_plural': 'Daily Activated Users',
            },
        ),
        migrations.CreateModel(
            name='DailyM2',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(unique=True)),
                ('total', models.IntegerField()),
            ],
            options={
                'verbose_name_plural': 'Daily M2',
            },
        ),
        migrations.CreateModel(
            name='DailyM3',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(unique=True)),
                ('total', models.IntegerField()),
            ],
            options={
                'verbose_name_plural': 'Daily M3',
            },
        ),
        migrations.CreateModel(
            name='DailyProjectsPerUser',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(unique=True)),
                ('total', models.IntegerField()),
            ],
            options={
                'verbose_name_plural': 'Daily Projects per User',
            },
        ),
        migrations.CreateModel(
            name='DailyRealUsers',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(unique=True)),
                ('total', models.IntegerField()),
            ],
            options={
                'verbose_name_plural': 'Daily Real Users',
            },
        ),
        migrations.CreateModel(
            name='MonthlyActivatedUsers',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(unique=True)),
                ('total', models.IntegerField()),
            ],
            options={
                'verbose_name_plural': 'Monthly Activated Users',
            },
        ),
        migrations.CreateModel(
            name='MonthlyM2',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(unique=True)),
                ('total', models.IntegerField()),
            ],
            options={
                'verbose_name_plural': 'Monthly M2',
            },
        ),
        migrations.CreateModel(
            name='MonthlyM3',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(unique=True)),
                ('total', models.IntegerField()),
            ],
            options={
                'verbose_name_plural': 'Monthly M3',
            },
        ),
        migrations.CreateModel(
            name='MonthlyProjectsPerUser',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(unique=True)),
                ('total', models.IntegerField()),
            ],
            options={
                'verbose_name_plural': 'Monthly Projects per User',
            },
        ),
        migrations.CreateModel(
            name='MonthlyRealUsers',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(unique=True)),
                ('total', models.IntegerField()),
            ],
            options={
                'verbose_name_plural': 'Monthly Real Users',
            },
        ),
    ]