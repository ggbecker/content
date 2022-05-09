#!/usr/bin/python3

from __future__ import print_function

import os
import sys

import ssg.constants
import ssg.environment
import ssg.jinja
import ssg.oval
import ssg.rules
import ssg.utils
import ssg.yaml
import ssg.build_yaml
import ssg.rule_yaml

def files(path):
    for file in os.listdir(path):
        if os.path.isfile(os.path.join(path, file)) and ("pass.sh" in file or "fail.sh" in file or "notapplicable.sh" in file or "error.sh" in file):
            # print(os.path.join(path, file))
            yield file

def main():
    ssg_root = "."
    ssg_build_config_yaml = "build/build_config.yml"

    known_dirs = set()
    for product in ssg.constants.product_directories:
        if product != sys.argv[1]:
            continue
        product_dir = os.path.join(ssg_root, "products", product)
        product_yaml_path = os.path.join(product_dir, "product.yml")
        product_yaml = ssg.yaml.open_raw(product_yaml_path)

        env_yaml = ssg.environment.open_environment(ssg_build_config_yaml, product_yaml_path)
        ssg.jinja.add_python_functions(env_yaml)

        guide_dir = os.path.join(product_dir, product_yaml['benchmark_root'])
        additional_content_directories = product_yaml.get("additional_content_directories", [])
        add_content_dirs = [os.path.abspath(os.path.join(product_dir, rd)) for rd in additional_content_directories]
        template_test_count = {}
        for cur_dir in [guide_dir] + add_content_dirs:
            if cur_dir not in known_dirs:
                for rule_dir in ssg.rules.find_rule_dirs(cur_dir):
                    rule_path = os.path.join(rule_dir, "rule.yml")
                    try:
                        rule = ssg.build_yaml.Rule.from_yaml(rule_path, env_yaml)
                    except ssg.build_yaml.DocumentationNotComplete:
                        # Happens on non-debug build when a rule is "documentation-incomplete"
                        continue
                    if rule.template:
                        # print(rule.template["name"])


                        
                        rule_tests = os.path.join(rule_dir, "tests")
                        try:
                            tests = files(rule_tests)
                            # i+=len(list(tests))
                            current_count = template_test_count.get(rule.template["name"])
                            if current_count:
                                template_test_count[rule.template["name"]] = current_count + len(list(tests))
                            else:
                                template_test_count[rule.template["name"]] = len(list(tests))
                            # for test in tests:
                            #     i+=1
                            #     print(os.path.join(rule_tests, test))
                        except FileNotFoundError:
                            continue

        tests_count_all = 0
        for template, tests_count in template_test_count.items():
            print(tests_count, '\t', template)
            tests_count_all+=tests_count

        print("Number of tests in rules that are templated:", tests_count_all, "in", product)


if __name__ == "__main__":
    main()
