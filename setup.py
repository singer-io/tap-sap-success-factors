#!/usr/bin/env python

from setuptools import find_packages, setup

setup(
    name="tap-sap-success-factors",
    version="0.0.1",
    description="Singer.io tap for extracting data from SAP SuccessFactors OData v2 APIs",
    author="Singer Community",
    url="http://singer.io",
    classifiers=["Programming Language :: Python :: 3 :: Only"],
    py_modules=["tap_sap_success_factors"],
    install_requires=[
        "singer-python==6.8.0",
        "requests==2.34.2",
        "backoff==2.2.1",
        "python-dateutil==2.9.0.post0",
    ],
    entry_points="""
          [console_scripts]
          tap-sap-success-factors=tap_sap_success_factors:main
      """,
    packages=find_packages(),
    include_package_data=True,
)
