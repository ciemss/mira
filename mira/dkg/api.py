"""API endpoints."""

from typing import Any, List, Mapping, Optional, Tuple, Union

from fastapi import APIRouter, Body, Path, Query, Request
from neo4j.graph import Relationship
from pydantic import BaseModel, Field
from typing_extensions import Literal

from mira.dkg.client import Entity, AskemEntity

__all__ = [
    "api_blueprint",
]

api_blueprint = APIRouter()


class RelationQuery(BaseModel):
    """A query for relations in the domain knowledge graph."""

    source_type: Optional[str] = Field(description="The source type (i.e., prefix)", example="vo")
    source_curie: Optional[str] = Field(
        description="The source compact URI (CURIE)", example="doid:946"
    )
    target_type: Optional[str] = Field(
        description="The target type (i.e., prefix)", example="ncbitaxon"
    )
    target_curie: Optional[str] = Field(
        description="The target compact URI (CURIE)", example="ncbitaxon:10090"
    )
    relations: Union[None, str, List[str]] = Field(
        description="A relation string or list of relation strings", example="vo:0001243"
    )
    relation_direction: Literal["right", "left", "both"] = Field(
        "right", description="The direction of the relationship"
    )
    relation_min_hops: int = Field(
        1, description="The minimum number of relationships between the subject and object.", ge=1
    )
    relation_max_hops: int = Field(
        1,
        description="The maximum number of relationships between the subject and object. Set to 0 to make infinite.",
        ge=0,
    )
    limit: Optional[int] = Field(
        description="A limit on the number of records returned", example=50, ge=0
    )
    full: bool = Field(
        False,
        description="A flag to turn on full entity and relation metadata return. Warning, this gets pretty verbose.",
    )
    distinct: bool = Field(
        False, description="A flag to turn on the DISTINCT flag in the return of a cypher query"
    )


@api_blueprint.get(
    "/entity/{curie}",
    # Note the order is important here - is greedy from left to right
    response_model=Union[AskemEntity, Entity],
    response_model_exclude_unset=True,
    response_model_exclude_defaults=True,
    response_model_exclude_none=True,
    tags=["entities"],
)
def get_entity(
    request: Request,
    curie: str = Path(
        ...,
        description="A compact URI (CURIE) for an entity in the form of ``<prefix>:<local unique identifier>``",
        example="ido:0000511",
    ),
):
    """Get information about an entity (e.g., its name, description synonyms, alternative identifiers,
    database cross-references, etc.) debased on its compact URI (CURIE).
    """
    return request.app.state.client.get_entity(curie)


@api_blueprint.get(
    "/lexical",
    response_model=List[Entity],
    tags=["entities"],
    response_model_include={"name", "synonyms", "description", "id"},
    response_model_exclude_unset=True,
    response_description="A successful response contains a list of Entity objects, subset to only "
    "include the id, name, synonyms, and description fields. Note that below "
    "in the example, several additional fields are shown, but they are not actually returned.",
)
def get_lexical(request: Request):
    """Get lexical information (i.e., name, synonyms, and description) for all entities in the graph."""
    return request.app.state.client.get_lexical()


class RelationResponse(BaseModel):
    """A triple (or multi-predicate triple) with abbreviated data."""

    subject: str = Field(description="The CURIE of the subject of the triple", example="doid:96")
    predicate: Union[str, List[str]] = Field(
        description="A predicate or list of predicates as CURIEs",
        example="ro:0002452",
    )
    object: str = Field(description="The CURIE of the object of the triple", example="symp:0000001")


class FullRelationResponse(BaseModel):
    """A triple (or multi-preficate triple) with full data."""

    subject: Entity
    predicate: Union[Mapping[str, Any], List[Mapping[str, Any]]]
    object: Entity


@api_blueprint.post(
    "/relations",
    response_model=Union[List[RelationResponse], List[FullRelationResponse]],
    tags=["relations"],
)
def get_relations(
    request: Request,
    relation_query: RelationQuery = Body(
        ...,
        examples={
            "source type query": {
                "summary": "Query relations with a given source node type",
                "value": {
                    "source_type": "vo",
                    "limit": 2,
                },
            },
            "target type query": {
                "summary": "Query relations with a given target node type",
                "value": {
                    "target_type": "stmp",
                    "limit": 2,
                },
            },
            "source/target types query": {
                "summary": "Query relations with given source/target types",
                "value": {
                    "source_type": "doid",
                    "target_type": "symp",
                    "limit": 2,
                },
            },
            "source query": {
                "summary": "Query relations with given source node, by CURIE",
                "value": {
                    "source_node": "doid:946",
                },
            },
            "target query": {
                "summary": "Query relations with given target node, by CURIE",
                "value": {
                    "target_node": "symp:0000570",
                },
            },
            "single relation type query": {
                "summary": "Query relations with given single relation type",
                "value": {"relation": "rdfs:subClassOf", "limit": 2},
            },
            "multiple relation type query": {
                "summary": "Query relations with given relation types",
                "value": {"relation": ["rdfs:subClassOf", "bfo:0000050"], "limit": 2},
            },
            "increase path length of query": {
                "summary": "Query a given fixed number of hops",
                "value": {
                    "source_curie": "bfo:0000002",
                    "relation": "rdfs:subClassOf",
                    "relation_max_hops": 2,
                    "limit": 2,
                },
            },
            "increase path length of query": {
                "summary": "Query a variable number of hops",
                "description": "Distinct is given as true since there might be multiple paths from the source to each given target.",
                "value": {
                    "source_curie": "bfo:0000002",
                    "relation": "rdfs:subClassOf",
                    "relation_max_hops": 0,
                    "limit": 2,
                    "distinct": True,
                },
            },
            "full results with single relation": {
                "summary": "Example query with a single predicate returning full data",
                "value": {
                    "target_curie": "symp:0000570",
                    "limit": 2,
                    "full": True,
                },
            },
            "full results with multiple relations relation": {
                "summary": "Example query with multiple predicates returning full data",
                "value": {
                    "source_curie": "bfo:0000002",
                    "relation": "rdfs:subClassOf",
                    "relation_max_hops": 0,
                    "limit": 2,
                    "distinct": True,
                    "full": True,
                },
            },
        },
    ),
):
    """Get relations based on the query sent.

    The question *which hosts get immunized by the Brucella
    abortus vaccine strain 19?* translates to the following query:

        {"source_curie": "vo:0000022", "relation": "vo:0001243"}

    The question *which strains immunize mice?* translates
    to the following query:

        {"target_curie": "ncbitaxon:10090", "relation": vo:0001243"}

    Note that you will rarely use all possible values in this endpoint at the same time.
    """
    records = request.app.state.client.query_relations(
        source_type=relation_query.source_type,
        source_curie=relation_query.source_curie,
        relation_name="r",
        relation_type=relation_query.relations,
        relation_direction=relation_query.relation_direction,
        relation_min_hops=relation_query.relation_min_hops,
        relation_max_hops=relation_query.relation_max_hops,
        target_name="t",
        target_type=relation_query.target_type,
        target_curie=relation_query.target_curie,
        full=relation_query.full,
        distinct=relation_query.distinct,
        limit=relation_query.limit,
    )
    if relation_query.full:
        return [
            FullRelationResponse(
                subject=Entity.from_data(s),
                predicate=dict(p) if isinstance(p, Relationship) else [dict(r) for r in p],
                object=Entity.from_data(o),
            )
            for s, p, o in records
        ]
    else:
        return [RelationResponse(subject=s, predicate=p, object=o) for s, p, o in records]


@api_blueprint.get(
    "/search",
    response_model=List[Union[AskemEntity, Entity]],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    response_model_exclude_defaults=True,
    tags=["grounding"],
)
def search(
    request: Request,
    q: str = Query(..., example="infect"),
    limit: int = 25,
    offset: int = 0,
):
    """Get nodes based on a search to their name/synonyms."""
    return request.app.state.client.search(q, limit=limit, offset=offset)
