"""Module to convert dictionaries to RDF graphs."""

import ast
from contextlib import suppress
import pandas as pd
import dateutil.parser as dateparser
from rdflib import BNode, Graph, URIRef
from rdflib.namespace import DC, FOAF, RDF, RDFS, SDO

from . import Node
from .faker.faker import Faker
from .incrementals.incrementals import Incremental
from .null_objects.factory import Boolean, DateTime, Double, Float, Integer, String
from .null_objects.null_objects import NoneNode
from .null_objects.safe_objects import SafeGraph, SafeNamespace
from .wrappers.wrappers import default_to_incremental, default_to_NoneNode

PR = SafeNamespace(
    #"https://raw.githubusercontent.com/fdioguardi/pronto/main/ontology/pronto.owl#"
    "https://raw.githubusercontent.com/jwackito/csv2pronto/main/ontology/pronto.owl#"
)
SIOC = SafeNamespace("http://rdfs.org/sioc/ns#")
GR = SafeNamespace("http://purl.org/goodrelations/v1#")
REC = SafeNamespace("https://w3id.org/rec/core/")
BUILDING = SafeNamespace("https://w3id.org/rec/building/")

def create_graph_from_chunk(df: pd.DataFrame, graph, idx, destination, format) -> Graph:
    """
    Writes a partial graph `g` with the info of a chunk of rows.

    Args:
        df (pd.DataFrame): a Pandas Dataframe with the info to add to `g`.
    """
    for i in range(len(df)):
        graph += create_graph(df.iloc[i].to_dict())
    graph.serialize(destination+f'.{idx:03}', format=format)


def create_graph_real_estate(row: dict) -> Graph:
    """
    Return a graph `g` with the info on `row`.

    Args:
        row (dict): Dictionary with the info to add.
    """

    row = {k: v for k, v in row.items() if v != ""}
    row = Faker.anonymize(row)

    g: Graph = SafeGraph()

    #listing = add_listing(g, row)
    #agent, account = add_agent(g, row)
    real_estate = add_real_estate(g, row)

    #g.add((listing, SIOC.has_creator, account))
    #g.add((account, SIOC.creator_of, listing))
    #g.add((listing, FOAF.maker, agent))
    #g.add((agent, FOAF.made, listing))

    #g.add((listing, SIOC.about, real_estate))

    #g.add((real_estate, PR.managed_by, agent))
    #g.add((agent, PR.manages, real_estate))

    return g


def create_graph(row: dict) -> Graph:
    """
    Return a graph `g` with the info on `row`.

    Args:
        row (dict): Dictionary with the info to add.
    """

    row = {k: v for k, v in row.items() if v != ""}
    row = Faker.anonymize(row)

    g: Graph = SafeGraph()

    listing = add_listing(g, row)
    agent, account = add_agent(g, row)
    real_estate = add_real_estate(g, row)

    g.add((listing, SIOC.has_creator, account))
    g.add((account, SIOC.creator_of, listing))
    g.add((listing, FOAF.maker, agent))
    g.add((agent, FOAF.made, listing))

    g.add((listing, SIOC.about, real_estate))

    g.add((real_estate, PR.managed_by, agent))
    g.add((agent, PR.manages, real_estate))

    return g


def add_listing(g: Graph, row: dict) -> Node:
    """Add listing to the graph `g` and return the listing's `Node`."""

    @default_to_incremental(PR, Incremental.LISTING)
    def _create_listing():
        return PR[f"listing_{row['site']}_{row['listing_id']}"]

    listing: Node = _create_listing()
    g.add((listing, RDF.type, PR.RealEstateListing))

    if row.get("url"):
        g.add((listing, SIOC.link, URIRef(row["url"])))
    g.add((listing, RDFS.label, String(row.get("title"))))
    g.add((listing, RDFS.comment, String(row.get("description"))))

    ###

    if row.get("transaction"):
        buisness_func = (
            GR.Sell if row["transaction"].lower() == "venta" else GR.LeaseOut
        )
        g.add((listing, GR.hasBuisnessFunction, buisness_func))

    ###

    # remove?
    site: Node = PR[row["site"]]
    g.add((listing, SIOC.has_space, site))
    g.add((site, SIOC.space_of, listing))

    ###

    g.add((listing, SIOC.id, String(row.get("listing_id"))))

    if row.get("date_extracted"):
        date = dateparser.parse(row["date_extracted"])
        g.add((listing, SIOC.read_at, DateTime(date)))

    if row.get("date_published"):
        date = dateparser.parse(row["date_published"])
        g.add((listing, DC.date, DateTime(date)))

    ###

    if row.get("price") and row.get("currency"):
        price: Node = add_price(g, row["price"], row["currency"], "BASE")
        g.add((listing, GR.hasPriceSpecification, price))

    if row.get("maintenance_fee") and row.get("maintenance_fee_currency"):
        expenses: Node = add_price(
            g,
            row.get("maintenance_fee", ""),
            row.get("maintenance_fee_currency", ""),
            "MAINTENANCE FEE",
        )

        g.add((listing, GR.hasPriceSpecification, expenses))

    ###

    return listing


def add_price(g: Graph, value: float, currency: str, p_type: str) -> Node:
    """Add price to the graph `g` and return the price's `Node`."""

    price: Node = BNode()
    g.add((price, RDF.type, GR.UnitPriceSpecification))
    g.add((price, GR.hasCurrencyValue, Float(value)))
    g.add((price, GR.hasCurrency, String(currency)))
    g.add((price, GR.priceType, String(p_type)))

    return price


def add_agent(g: Graph, row: dict) -> tuple[Node, Node]:
    """
    Add real estate agent to the graph `g` and return a tuple with the
    `Node`s of the agent and its user account.
    """

    @default_to_NoneNode
    def _create_agent():
        return PR[f"agent_{row['advertiser_name']}"]

    @default_to_NoneNode
    def _create_account():
        return PR[f"account_{row['site']}_{row['advertiser_id']}"]

    agent: Node = _create_agent()
    account: Node = _create_account()

    g.add((agent, RDF.type, FOAF.Agent))
    g.add((account, RDF.type, SIOC.UserAccount))

    g.add((account, SIOC.id, String(row.get("advertiser_id"))))
    g.add((account, SIOC.name, String(row.get("advertiser_name"))))
    g.add((agent, FOAF.account, account))
    g.add((account, SIOC.account_of, agent))

    return agent, account


def add_real_estate(g: Graph, row: dict) -> Node:
    """
    Add real estate to the graph `g` and return the real estate's
    `Node`.
    """

    @default_to_incremental(PR, Incremental.REAL_ESTATE)
    def _create_real_estate():
        return PR[f"real_estate_{row['site']}_{row['listing_id']}"]

    @default_to_incremental(PR, Incremental.SPACE)
    def _create_space():
        return PR[f"space_{row['site']}_{row['listing_id']}"]

    real_estate: Node = _create_real_estate()
    space: Node = _create_space()  # si un real estate no tiene space:

    g.add((real_estate, RDF.type, REC.RealEstate))
    g.add((space, RDF.type, REC.Space))

    g.add((real_estate, REC.includes, space))
    g.add((space, SDO.address, String(row.get("address"))))
    g.add((space, SDO.latitude, Double(row.get("latitude"))))
    g.add((space, SDO.longitude, Double(row.get("longitude"))))

    if row.get("year_built"):
        g.add((space, SDO.yearBuilt, Integer(int(float(row.get("year_built", 0))))))

    property_mapping = {
        "is_new_property": PR.is_brand_new,
        "is_finished": PR.is_finished,
        "is_studio_apartment": PR.is_studio_apartment,
    }

    for name, p in property_mapping.items():
        g.add((space, p, Boolean(None if row.get(name) == "" else row.get(name))))

    g.add((space, PR.luminosity, String(row.get("luminosity"))))
    g.add((space, PR.orientation, String(row.get("orientation"))))
    g.add((space, PR.disposition, String(row.get("disposition"))))
    g.add((space, PR.property_type, String(row.get("property_type"))))

    # add features
    features: dict = ast.literal_eval(row.get("features") or "{}")
    for feature, value in features.items():
        f: Node = PR[f"feature_{feature}_{value}"]
        g.add((f, RDF.type, PR.Feature))
        g.add((space, PR.has_feature, f))
        g.add((f, RDFS.label, String(f"{feature}: {value}")))
        g.add((f, DC.title, String(feature)))
        g.add((f, PR.has_value, String(value)))

    # add surfaces
    for s in ["total", "covered", "uncovered", "land"]:
        with suppress(KeyError):
            value = row[f"{s}_surface"] or row[f"reconstructed_{s}_surface"]
            unit = row[f"{s}_surface_unit"] or row[f"reconstructed_{s}_surface_unit"]

            if value and unit:
                add_surface(g, space, value, unit, s)

    # add amount of rooms
    g.add((space, PR.has_amount_of_rooms, Integer(row.get("room_amnt"))))
    rooms: dict[str, Node] = {
        "bath": BUILDING.Bathroom,
        "garage": BUILDING.Garage,
        "bed": BUILDING.Bedroom,
        "toilette": BUILDING.Toilet,
    }
    for room, room_class in rooms.items():
        add_room(g, space, row, room, room_class)

    # add regions

    @default_to_NoneNode
    def _create_neighborhood():
        return PR[
            f"neibourhood_{row['province']}_{row['district']}_{row['neighborhood']}"
        ]

    @default_to_NoneNode
    def _create_district():
        return PR[f"district_{row['province']}_{row['district']}"]

    @default_to_NoneNode
    def _create_province():
        return PR[f"province_{row['province']}"]

    neighborhood: Node = _create_neighborhood()
    district: Node = _create_district()
    province: Node = _create_province()

    g.add((neighborhood, RDF.type, REC.Region))
    g.add((district, RDF.type, REC.Region))
    g.add((province, RDF.type, REC.Region))

    g.add((neighborhood, RDFS.label, String(row.get("neighborhood"))))
    g.add((district, RDFS.label, String(row.get("district"))))
    g.add((province, RDFS.label, String(row.get("province"))))

    g.add((space, REC.locatedIn, neighborhood))
    g.add((space, REC.locatedIn, district))
    g.add((space, REC.locatedIn, province))

    g.add((neighborhood, REC.locatedIn, district))
    g.add((neighborhood, REC.locatedIn, province))

    g.add((district, REC.locatedIn, province))

    return real_estate


def add_surface(g: Graph, space: Node, value: float, unit: str, s_type: str) -> Node:
    """Add surface to the graph `g` and return the surface's `Node`."""

    surface: Node = BNode()

    g.add((surface, RDF.type, PR.SizeSpecification))
    g.add((surface, GR.hasValue, Float(value)))
    g.add((surface, GR.hasUnitOfMeasurement, String(unit)))
    g.add((surface, PR.size_type, String(s_type)))

    g.add((space, PR.hasSizeSpecification, surface))

    return surface


def add_room(g: Graph, space: Node, row: dict, room: str, room_class: Node) -> None:
    """Add rooms to the graph `g`."""

    amnt = row.get(f"{room}_amnt")
    if not amnt:
        return

    if not amnt.isdigit():
        return
    amnt = int(amnt)

    def _create_room() -> Node:
        fragment = getattr(space, "fragment", None)
        if not fragment:
            return BNode()
        return PR[f"{fragment}_{room}_{i}"]

    for i in range(amnt):
        r: Node = _create_room()
        g.add((r, RDF.type, room_class))
        g.add((space, REC.hasPart, r))
