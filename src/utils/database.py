from timy import timer
from os import getenv, path
from typing import Tuple, Union
from sqlalchemy import create_engine
from psycopg2 import connect, sql, OperationalError, errors
import pandas as pd

from src.utils.misc import repeat_token, delete_var, to_sql
from constants import FENCE, TABLES_INFO_DICT
from models import Database, TableInfo

def setup_database() -> Union[Database, None]:
    """
    Connects to a PostgreSQL database using environment variables for connection details.

    Returns:
        Database: A NamedTuple with engine and conn attributes for the database connection.
        None: If there was an error connecting to the database.
    
    >>> setup_database()
    """
    
    try:
        # Get environment variables
        user = getenv('POSTGRES_USER')
        passw = getenv('POSTGRES_PASSWORD')
        host = getenv('POSTGRES_HOST', 'localhost')
        port = getenv('POSTGRES_PORT', '5432')
        database = getenv('POSTGRES_DB')

        # Connect to the database
        db_uri = f'postgresql://{user}:{passw}@{host}:{port}/{database}'
        engine = create_engine(db_uri)
        
        db_info = f'dbname={database} user={user} host={host} port={port} password={passw}'
        conn = connect(db_info)

        print('Connection to the database established!')
        return Database(engine, conn)
    
    except OperationalError as e:
        print(f"Error connecting to database: {e}")
        return None

##########################################################################
## LOAD AND TRANSFORM
##########################################################################
def insert_data_on_database(
    database, file, table_name, columns, to_folder, 
    encoding, cleanse_transform_map
):
    
    print('Trabalhando no arquivo: ' + file + ' [...]')
    artefato = pd.DataFrame(columns=list(range(0, len(columns))))
    dtypes = {column: 'object' for column in columns}
    extracted_file_path = path.join(to_folder, file)
    
    artefato = pd.read_csv(
        filepath_or_buffer=extracted_file_path,
        sep=';', skiprows=0, header=None, dtype=dtypes, encoding=encoding,
    )

    # Tratamento do arquivo antes de inserir na base:
    artefato = artefato.reset_index()
    del artefato['index']

    # Renomear colunas
    artefato.columns = columns

    artefato = cleanse_transform_map(artefato)

    # Gravar dados no banco:
    artefato.to_sql(name=table_name, con=database.engine, if_exists='append', index=False)
    print('Arquivos ' + file + ' inserido com sucesso no banco de dados!')

def populate_table_with_filename(
    database: Database, 
    table_info: TableInfo,
    to_folder: str,
    filename: str
): 
    enum_columns = list(range(0, len(table_info.columns)))
    artefato = pd.DataFrame(columns=enum_columns)
    dtypes = { column: 'object' for column in table_info.columns }
    extracted_file_path = path.join(to_folder, filename)

    artefato = pd.read_csv(
        filepath_or_buffer=extracted_file_path,
        sep=';', skiprows=0, header=None, dtype=dtypes, encoding=table_info.encoding,
    )

    # Tratamento do arquivo antes de inserir na base:
    artefato = artefato.reset_index()
    del artefato['index']

    # Renomear colunas
    artefato.columns = table_info.columns
    artefato = table_info.transform_map(artefato)

    # Gravar dados no banco:
    to_sql(artefato, name=table_info.table_name, con=database.engine, if_exists='append', index=False)
    print('Arquivos ' + filename + ' inserido com sucesso no banco de dados!')

    delete_var(artefato)

@timer('Popular tabela')
def populate_table_with_filenames(
    database: Database, 
    table_info: TableInfo, 
    from_folder: str,
    filenames: list
):
    title=f'## Arquivos de {table_info.label.upper()}:'
    header=f'{FENCE}\n{title}\n{FENCE}'
    print(header)

    # Drop table antes do insert
    with database.conn.cursor() as cur:
        identifier = sql.Identifier(table_info.table_name)
        query = sql.SQL('DROP TABLE IF EXISTS {};').format(identifier)
        cur.execute(query)
        database.conn.commit()

    # Inserir dados
    for filename in filenames:
        print('Trabalhando no arquivo: ' + filename + ' [...]')
        try:
            populate_table_with_filename(database, table_info, from_folder, filename)

        except Exception as e:
            print(f'Falha em salvar arquivo {filename} em tabela {table_info.table_name}. Erro: {e}')

    print(f'Arquivos de {table_info.label} finalizados!')

@timer(ident='Popular banco')
def populate_database(database, from_folder, files):
    table_names = list(TABLES_INFO_DICT.keys())

    for table_name in table_names:
        label = TABLES_INFO_DICT['label']
        columns = TABLES_INFO_DICT['columns']
        expression = TABLES_INFO_DICT['expression']
        transform_map = TABLES_INFO_DICT['transform_map']
        encoding = TABLES_INFO_DICT['encoding']

        table_info = TableInfo(label, table_name, columns, encoding, transform_map)
        populate_table_with_filenames(database, table_info, from_folder, files[table_name])

@timer('Criar indices do banco')
def generate_database_indices(conn):
    cur = conn.cursor()

    print("""
    #############################################
    ## Processo de carga dos arquivos finalizado!
    #############################################
    """)

    # Criar índices na base de dados:
    print("""
    #######################################
    ## Criar índices na base de dados [...]
    #######################################
    """)

    cur.execute("""
    create index empresa_cnpj on empresa(cnpj_basico);
    commit;
    create index estabelecimento_cnpj on estabelecimento(cnpj_basico);
    commit;
    create index socios_cnpj on socios(cnpj_basico);
    commit;
    create index simples_cnpj on simples(cnpj_basico);
    commit;
    """)
    
    conn.commit()
    print("""
    ############################################################
    ## Índices criados nas tabelas, para a coluna `cnpj_basico`:
    - empresa
    - estabelecimento
    - socios
    - simples
    ############################################################
    """)