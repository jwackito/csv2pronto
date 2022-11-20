"""Module to convert dictionaries to RDF graphs."""

import ast
from contextlib import suppress

import dateutil.parser as dateparser
from rdflib import BNode, Graph, URIRef
from rdflib.namespace._DC import DC
from rdflib.namespace._FOAF import FOAF
from rdflib.namespace._RDF import RDF
from rdflib.namespace._RDFS import RDFS
from rdflib.namespace._SDO import SDO

from helpers import (
    Boolean,
    DateTime,
    Double,
    Float,
    Incremental,
    Integer,
    Node,
    NoneNode,
    SafeGraph,
    SafeNamespace,
    String,
    default_to_NoneNode,
    default_to_incremental,
)

PR = SafeNamespace(
    "https://raw.githubusercontent.com/fdioguardi/pronto/main/ontology/pronto.owl#"
)
SIOC = SafeNamespace("http://rdfs.org/sioc/ns#")
GR = SafeNamespace("http://purl.org/goodrelations/v1#")
REC = SafeNamespace("https://w3id.org/rec/core/")
BUILDING = SafeNamespace("https://w3id.org/rec/building/")


def create_graph(context: Graph, row: dict) -> Graph:
    """
    Return a graph `g` with the info on `row`.

    Args:
        context (Graph): Graph with previously added info.
        row (dict): Dictionary with the info to add.
    """

    row = {k: v for k, v in row.items() if v != ""}

    g: Graph = SafeGraph()

    listing = add_listing(g, row)
    agent, account = add_agent(context, g, row)
    real_estate = add_real_estate(g, row)

    g.add((listing, SIOC.has_creator, account))
    g.add((account, SIOC.creator_of, listing))

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
        buisness_func = GR.Sell if row["transaction"] == "Venta" else GR.LeaseOut
        g.add((listing, GR.hasBuisnessFunction, buisness_func))

    ###

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


def add_agent(context: Graph, g: Graph, row: dict) -> tuple[Node, Node]:
    """
    Add real estate agent to the graph `g` and return a tuple with the
    `Node`s of the agent and its user account.
    """

    @default_to_NoneNode
    def _create_agent():
        if row.get("advertiser_name"):
            return PR[f"agent_{row['advertiser_name']}"]

        account: Node = PR[f"account_{row['site']}_{row['advertiser_id']}"]
        agent = context.value(account, SIOC.account_of) or NoneNode()
        assert isinstance(agent, Node)
        return agent

    @default_to_NoneNode
    def _create_account():
        if row.get("advertiser_id"):
            return PR[f"account_{row['site']}_{row['advertiser_id']}"]

        agent: Node = PR[f"agent_{row['advertiser_name']}"]
        account = context.value(agent, SIOC.account) or NoneNode()
        assert isinstance(account, Node)
        return account

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

    is_new_property = row.get("is_new_property")
    is_finished = row.get("is_finished")
    is_studio_apartment = row.get("is_studio_apartment")
    if is_new_property != "":
        g.add((space, PR.is_brand_new, Boolean(is_new_property)))
    if is_finished != "":
        g.add((space, PR.is_finished, Boolean(is_finished)))
    if is_studio_apartment != "":
        g.add((space, PR.is_studio_apartment, Boolean(row.get("is_studio_apartment"))))

    g.add((space, PR.luminosity, String(row.get("luminosity"))))
    g.add((space, PR.orientation, String(row.get("orientation"))))
    g.add((space, PR.disposition, String(row.get("disposition"))))
    g.add((space, PR.property_type, String(row.get("property_type"))))

    # add features
    features: dict = ast.literal_eval(row.get("features") or "{}")
    for feature, value in features.items():
        f: Node = PR[feature]
        g.add((f, RDF.type, PR.Feature))
        g.add((space, PR.has_feature, f))
        g.add((f, RDFS.label, String(feature)))
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
    g.add((surface, PR.has_surface_value, Float(value)))
    g.add((surface, GR.has_unit_of_measurement, String(unit)))
    g.add((surface, PR.surface_type, String(s_type)))

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
