"""Compile real normalization macros and check valid/invalid values in ClickHouse.

uv run --locked python tests/staging/integration.py
Only SELECT queries are executed; no databases or source records are changed.
"""
from pathlib import Path
from decimal import Decimal
import os
import shutil
import subprocess
import tempfile

import clickhouse_connect
from clickhouse_connect.driver.exceptions import DatabaseError

ROOT = Path(__file__).resolve().parents[2]
# Values are bound as parameters, never interpolated into SQL.
CASES = [
    ('trim', '\t Drug \r\n', [], "CAST(value AS String)", 'Drug'),
    ('unicode_space', '\u00a0Drug\u00a0', [], "CAST(value AS String)", 'Drug'),
    ('blank', ' \t\r\n', [], "CAST(value AS Nullable(String))", None),
    ('null', None, [], "CAST(value AS Nullable(String))", None),
    ('marker', ' n/A ', ['-', 'null', 'none', 'n/a'], "CAST(value AS Nullable(String))", None),
    ('preserve_na_code', 'NA', [], "CAST(value AS String)", 'NA'),
    ('preserve_na_identifier', 'N/A', [], "CAST(value AS String)", 'N/A'),
    ('preserve_zero_code', '000123', [], "CAST(value AS String)", '000123'),
    ('batch_marker', ' - ', ['-'], "CAST(value AS Nullable(String))", None),
    ('required_missing', ' ', [], "CAST(value AS String)", 'ERROR'),
    ('required_dictionary_missing', ' ', [], "CAST(value AS LowCardinality(String))", 'ERROR'),
    ('id', '4294967295', [], "{{ stg_integer('value', 'UInt32', positive=true) }}", 4294967295),
    ('id_overflow', '4294967296', [], "{{ stg_integer('value', 'UInt32', positive=true) }}", 'ERROR'),
    ('id_negative', '-1', [], "{{ stg_integer('value', 'UInt32', positive=true) }}", 'ERROR'),
    ('id_zero', '0', [], "{{ stg_integer('value', 'UInt32', positive=true) }}", 'ERROR'),
    ('id_fraction', '1.5', [], "{{ stg_integer('value', 'UInt32', positive=true) }}", 'ERROR'),
    ('optional_id', '-', ['-'], "{{ stg_integer('value', 'Nullable(UInt32)', positive=true) }}", None),
    ('count_zero', '0', [], "{{ stg_integer('value', 'UInt16') }}", 0),
    ('count_overflow', '65536', [], "{{ stg_integer('value', 'UInt16') }}", 'ERROR'),
    ('tier_overflow', '256', [], "{{ stg_integer('value', 'Nullable(UInt8)', positive=true) }}", 'ERROR'),
    ('decimal_negative', '-525.123456', [], "{{ stg_decimal('value', 'Decimal(18, 6)') }}", '-525.123456'),
    ('decimal_zero', '0', [], "{{ stg_decimal('value', 'Decimal(18, 6)') }}", '0.000000'),
    ('decimal_zeros', '1.12345600', [], "{{ stg_decimal('value', 'Decimal(18, 6)') }}", '1.123456'),
    ('decimal_precision', '1.1234567', [], "{{ stg_decimal('value', 'Decimal(18, 6)') }}", 'ERROR'),
    ('decimal_overflow', '1000000000000', [], "{{ stg_decimal('value', 'Decimal(18, 6)') }}", 'ERROR'),
    ('decimal_nan', 'NaN', [], "{{ stg_decimal('value', 'Nullable(Decimal(18, 6))') }}", 'ERROR'),
    ('decimal_missing', '-', ['-'], "{{ stg_decimal('value', 'Nullable(Decimal(18, 6))') }}", None),
    ('decimal_null', None, [], "{{ stg_decimal('value', 'Nullable(Decimal(18, 6))') }}", None),
    ('decimal_infinity', 'Infinity', [], "{{ stg_decimal('value', 'Decimal(18, 6)') }}", 'ERROR'),
    ('decimal_comma_rejected', '1,000', [], "{{ stg_decimal('value', 'Decimal(18, 6)') }}", 'ERROR'),
    ('percent_comma', ' 2,86% ', [], "{{ stg_decimal('value', 'Decimal(9, 4)', precision=9, scale=4, percentage=true) }}", '2.8600'),
    ('percent_full', '100%', [], "{{ stg_decimal('value', 'Decimal(9, 4)', precision=9, scale=4, percentage=true) }}", '100.0000'),
    ('percent_negative', '-1', [], "{{ stg_decimal('value', 'Decimal(9, 4)', precision=9, scale=4, percentage=true) }}", 'ERROR'),
    ('percent_too_high', '100.0001', [], "{{ stg_decimal('value', 'Decimal(9, 4)', precision=9, scale=4, percentage=true) }}", 'ERROR'),
    ('percent_precision', '0.00001', [], "{{ stg_decimal('value', 'Decimal(9, 4)', precision=9, scale=4, percentage=true) }}", 'ERROR'),
    ('leap_day', '2024-02-29', [], "{{ stg_date('value', 'Date32') }}", '2024-02-29'),
    ('invalid_day', '2024-02-30', [], "{{ stg_date('value', 'Date32') }}", 'ERROR'),
    ('optional_invalid_day', '2024-02-30', [], "{{ stg_date('value', 'Nullable(Date32)') }}", 'ERROR'),
    ('invalid_leap', '2023-02-29', [], "{{ stg_date('value', 'Date32') }}", 'ERROR'),
    ('date_overflow', '2500-01-01', [], "{{ stg_date('value', 'Date32') }}", 'ERROR'),
    ('zero_date_marker', '0000-00-00', ['0000-00-00'], "{{ stg_date('value', 'Nullable(Date32)') }}", None),
    ('epoch_is_valid', '1970-01-01', [], "{{ stg_date('value', 'Date32') }}", '1970-01-01'),
    ('timestamp_microseconds', '2024-02-29T12:34:56.123456', [], "{{ stg_timestamp('value', 'DateTime64(6)') }}", '2024-02-29 12:34:56.123456'),
    ('timestamp_seconds', '2024-02-29 12:34:56', [], "{{ stg_timestamp('value', 'DateTime64(6)') }}", '2024-02-29 12:34:56.000000'),
    ('timestamp_invalid_date', '2024-02-30 12:34:56', [], "{{ stg_timestamp('value', 'DateTime64(6)') }}", 'ERROR'),
    ('optional_timestamp_invalid', 'not-a-date', [], "{{ stg_timestamp('value', 'Nullable(DateTime64(6))') }}", 'ERROR'),
    ('timestamp_overprecision', '2024-02-29 12:34:56.1234567', [], "{{ stg_timestamp('value', 'DateTime64(6)') }}", 'ERROR'),
    ('domain_case', ' pagi ', [], "{{ stg_domain('value', 'LowCardinality(Nullable(String))', ['PAGI', 'SORE']) }}", 'PAGI'),
    ('domain_spaces', ' Non\t Member ', [], "{{ stg_domain('value', 'LowCardinality(Nullable(String))', ['NON MEMBER', 'MEMBER']) }}", 'NON MEMBER'),
    ('domain_unknown', 'EVENING', [], "{{ stg_domain('value', 'LowCardinality(Nullable(String))', ['PAGI', 'SORE']) }}", 'ERROR'),
    ('domain_null', None, [], "{{ stg_domain('value', 'LowCardinality(Nullable(String))', ['PAGI', 'SORE']) }}", None),
    ('unknown_classification_valid', 'unknown', [], "{{ stg_domain('value', 'LowCardinality(Nullable(String))', ['UNKNOWN', 'SALE']) }}", 'UNKNOWN'),
]


def main():
    with tempfile.TemporaryDirectory(prefix='inventory-staging-rules-') as temp:
        project = Path(temp)
        (project / 'models').mkdir()
        shutil.copytree(ROOT / 'transform/dbt/macros', project / 'macros')
        (project / 'dbt_project.yml').write_text('name: normalization_rules\nversion: "1.0"\nconfig-version: 2\nprofile: inventory_dw\n')
        statements = []
        for name, _, missing, expression, _ in CASES:
            statements.append(f"-- CASE:{name}\nwith cleaned as (select {{{{ stg_text('input', {missing!r}) }}}} as value "
                              "from (select {input:Nullable(String)} as input))\nselect toString(" + expression + ') as result from cleaned')
        (project / 'models/fixture.sql').write_text('\n'.join(statements))
        env = {**os.environ, 'DBT_PROFILES_DIR': str(ROOT / 'transform/dbt'),
               'DBT_TARGET_PATH': str(project / 'target'), 'DBT_LOG_PATH': str(project / 'logs')}
        subprocess.run(['uv', 'run', '--locked', '--project', str(ROOT), 'dbt', 'compile', '--project-dir', str(project),
                        '--no-introspect', '--no-populate-cache'], env=env, check=True)
        queries = (project / 'target/compiled/normalization_rules/models/fixture.sql').read_text().split('-- CASE:')[1:]
        client = clickhouse_connect.get_client(host=os.environ.get('CLICKHOUSE_HOST','localhost'),
            port=int(os.environ.get('CLICKHOUSE_HTTP_PORT','8123')),username=os.environ.get('CLICKHOUSE_USER','dbt'),
            password=os.environ.get('CLICKHOUSE_PASSWORD','dbt_local'))
        try:
            for (name,value,_,expression,expected),statement in zip(CASES,queries,strict=True):
                compiled_name,query=statement.split('\n',1)
                assert compiled_name==name
                try:
                    actual=client.query(query,parameters={'input':value}).first_row[0]
                except DatabaseError:
                    if expected!='ERROR': raise
                else:
                    assert expected!='ERROR', (name, actual, expected)
                    if expected is not None and 'stg_decimal' in expression:
                        assert Decimal(actual)==Decimal(expected), (name, actual, expected)
                    else:
                        assert actual==(None if expected is None else str(expected)),(name,actual,expected)
            print(f'PASS: {len(CASES)} normalization, precision, domain and rejection cases')
        finally:
            client.close()


if __name__=='__main__':
    main()
