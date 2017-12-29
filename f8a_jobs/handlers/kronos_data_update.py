"""Class to append new data for Kronos training."""

from selinon import StoragePool
from sqlalchemy.exc import SQLAlchemyError
from selinon import StoragePool
# from f8a_worker.models import WorkerResult, Analysis

from .base import BaseHandler
import os


class KronosDataUpdater(BaseHandler):
    """Class to append new data for Kronos training."""

    def __init__(self, *args, **kwargs):
        """Initialize instance of the GitHubMostStarred class."""
        super().__init__(*args, **kwargs)
        self.ecosystem = None
        self.user_persona = None
        self.extra_manifest_list = []
        self.unique_packages = set()
        self.past_variable = None
        self.past_count = None

    def execute(self, ecosystem="maven",
                past_variable="DAYS",
                past_count=7):
        self.ecosystem = ecosystem
        self.past_variable = past_variable
        self.past_count = past_count
        return self.processing()

    def generate_query(self):
        query = "select all_details -> 'ecosystem' as ecosystem, all_details -> '_resolved' as deps from worker_results"
        query += " cross join jsonb_array_elements(worker_results.task_result -> 'result')"
        query += " all_results cross join jsonb_array_elements(all_results -> 'details') all_details where worker = 'GraphAggregatorTask'"
        query += " and EXTRACT({} FROM age(to_timestamp(task_result->'_audit'->>'started_at','YYYY-MM-DDThh24:mi:ss'))) <={} and all_details->>'ecosystem'='{}';".format(
            self.past_var, self.past_count, self.ecosystem)
        return query

    def execute_query(self, query):
        return self.postgres.session.query(query)

    def append_mainfest(self, s3):
        manifest_path = os.path.join(self.ecosystem,
                                     "github/data_input_manifest_file_list",
                                     self.user_persona, "manifets.json")
        manifest_data = s3.fetch_existing_data(manifest_path)
        for each in manifest_data:
            if each.get('ecosystem') == self.ecosystem:
                cur_package_list = each.get('package_list', [])
                cur_package_list.extend(self.extra_manifest_list)
                each['package_list'] = cur_package_list
                break
        s3.store_updated_data(manifest_data, manifest_path)

    def append_package_topic(self, s3):
        package_topic_path = os.path.join(self.ecosystem,
                                          "github/data_input_raw_package_list/package_topic.json")
        package_topic = s3.fetch_existing_data(package_topic_path)
        for each in package_topic:
            if each.get('ecosystem') == self.ecosystem:
                cur_package_list = each.get('package_topic_map', {})
                for each_package in self.unique_packages:
                    if each_package not in cur_package_list:
                        cur_package_list[each_pck] = []
                each['package_list'] = cur_package_list
                break
        s3.store_updated_data(package_topic, package_topic_path)

    def processing(self):
        result = self.execute_query(query).fetchall()
        for each_row in result:
            package_list = []
            if len(each_row) != 2 or each_row[0] != self.ecosystem:
                continue
            for dep in each_row[1]:
                package_name = dep.get('package')
                package_list.append(package_name)
                self.unique_packages.add(package_name)
                self.extra_manifest_list.append(package_list)

        s3 = StoragePool.get_connected_storage('S3KronosAppend')
        self.append_mainfest(s3)
        self.append_package_topic(s3)
