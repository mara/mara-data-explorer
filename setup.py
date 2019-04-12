from setuptools import setup, find_packages

setup(
    name='data-sets',
    version='1.0.1',

    description='Flask based UI for displaying & segmenting a single database table',

    install_requires=[
        'mara-db>=3.2.0',
        'mara-page>=1.3.0'
    ],

    dependency_links=[
    ],

    packages=find_packages(),

    author='Mara contributors',
    license='MIT',

    entry_points={},
)

