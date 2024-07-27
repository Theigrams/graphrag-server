import pandas as pd
import tiktoken
from graphrag.query.context_builder.builders import LocalContextBuilder
from graphrag.query.context_builder.entity_extraction import EntityVectorStoreKey
from graphrag.query.indexer_adapters import (
    read_indexer_covariates,
    read_indexer_entities,
    read_indexer_relationships,
    read_indexer_reports,
    read_indexer_text_units,
)
from graphrag.query.input.loaders.dfs import (
    store_entity_semantic_embeddings,
)
from graphrag.query.llm.base import BaseLLM, BaseTextEmbedding
from graphrag.query.structured_search.local_search.mixed_context import (
    LocalSearchMixedContext,
)
from graphrag.query.structured_search.local_search.search import LocalSearch
from graphrag.vector_stores.lancedb import LanceDBVectorStore

from webserver.utils import consts
from webserver.configs import settings


async def load_local_context(input_dir: str, embedder: BaseTextEmbedding, token_encoder: tiktoken.Encoding | None = None) -> LocalContextBuilder:
    # read nodes table to get community and degree data
    entity_df = pd.read_parquet(f"{input_dir}/{consts.ENTITY_TABLE}.parquet")
    entity_embedding_df = pd.read_parquet(f"{input_dir}/{consts.ENTITY_EMBEDDING_TABLE}.parquet")

    entities = read_indexer_entities(entity_df, entity_embedding_df, consts.COMMUNITY_LEVEL)

    # load description embeddings to an in-memory lancedb vectorstore
    # to connect to a remote db, specify url and port values.
    description_embedding_store = LanceDBVectorStore(
        collection_name="entity_description_embeddings",
    )
    description_embedding_store.connect(db_uri=settings.lancedb_uri)
    entity_description_embeddings = store_entity_semantic_embeddings(
        entities=entities, vectorstore=description_embedding_store
    )

    relationship_df = pd.read_parquet(f"{input_dir}/{consts.RELATIONSHIP_TABLE}.parquet")
    relationships = read_indexer_relationships(relationship_df)

    # covariate_df = pd.read_parquet(f"{settings.input_dir}/{consts.COVARIATE_TABLE}.parquet")
    # claims = read_indexer_covariates(covariate_df)
    # covariates = {"claims": claims}

    report_df = pd.read_parquet(f"{input_dir}/{consts.COMMUNITY_REPORT_TABLE}.parquet")
    reports = read_indexer_reports(report_df, entity_df, consts.COMMUNITY_LEVEL)

    text_unit_df = pd.read_parquet(f"{input_dir}/{consts.TEXT_UNIT_TABLE}.parquet")
    text_units = read_indexer_text_units(text_unit_df)

    context_builder = LocalSearchMixedContext(
        community_reports=reports,
        text_units=text_units,
        entities=entities,
        relationships=relationships,
        # covariates=covariates,
        entity_text_embeddings=description_embedding_store,
        embedding_vectorstore_key=EntityVectorStoreKey.ID,
        # if the vectorstore uses entity title as ids, set this to EntityVectorStoreKey.TITLE
        text_embedder=embedder,
        token_encoder=token_encoder,
    )
    return context_builder


async def build_local_search_engine(llm: BaseLLM, context_builder: LocalContextBuilder = None, token_encoder: tiktoken.Encoding | None = None) -> LocalSearch:
    local_context_params = {
        "text_unit_prop": 0.5,
        "community_prop": 0.1,
        "conversation_history_max_turns": 5,
        "conversation_history_user_turns_only": True,
        "top_k_mapped_entities": 10,
        "top_k_relationships": 10,
        "include_entity_rank": True,
        "include_relationship_weight": True,
        "include_community_rank": False,
        "return_candidate_context": False,
        "embedding_vectorstore_key": EntityVectorStoreKey.ID,
        # set this to EntityVectorStoreKey.TITLE if the vectorstore uses entity title as ids
        "max_tokens": settings.max_tokens,
        # change this based on the token limit you have on your model (if you are using a model with 8k limit, a good setting could be 5000)
    }
    llm_params = {
        "max_tokens": settings.max_tokens,
        "temperature": settings.temperature,
    }
    search_engine = LocalSearch(
        llm=llm,
        context_builder=context_builder,
        token_encoder=token_encoder,
        llm_params=llm_params,
        context_builder_params=local_context_params,
        response_type="multiple paragraphs",
        # free form text describing the response type and format, can be anything, e.g. prioritized list, single paragraph, multiple paragraphs, multiple-page report
    )
    return search_engine

# result = await local_search.asearch("Tell me about Agent Mercer")
# print(result.response)
#
# result.completion_time
# question = "Tell me about Dr. Jordan Hayes"
# result = await search_engine.asearch(question)
# print(result.response)


# result.context_data["entities"].head()
# result.context_data["relationships"].head()
# result.context_data["reports"].head()
# result.context_data["sources"].head()
# if "claims" in result.context_data:
#     print(result.context_data["claims"].head())
#
#
# question_generator = LocalQuestionGen(
#     llm=llm,
#     context_builder=context_builder,
#     token_encoder=token_encoder,
#     llm_params=llm_params,
#     context_builder_params=local_context_params,
# )
#
# question_history = [
#     "Tell me about Agent Mercer",
#     "What happens in Dulce military base?",
# ]
# candidate_questions = await question_generator.agenerate(
#     question_history=question_history, context_data=None, question_count=5
# )
# print(candidate_questions.response)