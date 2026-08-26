"""Authoritative Puerto Rico marine elevation dataset registry.

Registry entries are discovery anchors only.  Spatial inclusion still requires
intersection against the requested AOI/asset footprint, and derived DEMs do not
count as independent sensor acquisitions when they share an underlying survey.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DatasetRole(StrEnum):
    SENSOR_POINT_CLOUD = "SENSOR_POINT_CLOUD"
    DERIVED_DEM = "DERIVED_DEM"
    FUSED_COASTAL_DEM = "FUSED_COASTAL_DEM"


@dataclass(frozen=True, slots=True)
class MarineDatasetAnchor:
    dataset_id: str
    title: str
    role: DatasetRole
    provider: str
    landing_url: str
    bulk_url: str | None = None
    url_list_url: str | None = None
    notes: str = ""


PUERTO_RICO_MARINE_DATASETS: tuple[MarineDatasetAnchor, ...] = (
    MarineDatasetAnchor(
        dataset_id="9390",
        title="2019 NOAA NGS Topobathy Lidar: Puerto Rico",
        role=DatasetRole.SENSOR_POINT_CLOUD,
        provider="NOAA NGS / NOAA OCM",
        landing_url="https://www.fisheries.noaa.gov/inport/item/65546/full-list",
        bulk_url="https://noaa-nos-coastal-lidar-pds.s3.amazonaws.com/laz/geoid18/9390/",
        notes="LAZ bulk distribution; inventory/metadata must be checked for actual AOI overlap.",
    ),
    MarineDatasetAnchor(
        dataset_id="6211",
        title="2015 NOAA NGS Topobathy Lidar DEM: Puerto Rico",
        role=DatasetRole.DERIVED_DEM,
        provider="NOAA NGS / NOAA OCM",
        landing_url="https://coast.noaa.gov/htdata/raster2/elevation/PR_Puerto_Rico_NGS_DEM_2015_6211/",
        notes="Derived DEM from topobathy lidar; not independent from its source acquisition.",
    ),
    MarineDatasetAnchor(
        dataset_id="5154",
        title="2016 USACE NCMP Topobathy Lidar DEM: Puerto Rico",
        role=DatasetRole.DERIVED_DEM,
        provider="USACE / NOAA OCM",
        landing_url="https://coast.noaa.gov/htdata/raster2/elevation/USACE_PuertoRico_Topobathy_prvd02_DEM_2016_5154/",
        notes="PRVD02 DEM distribution; retain vertical-datum identity before comparison.",
    ),
    MarineDatasetAnchor(
        dataset_id="8571",
        title="2018 USACE FEMA Topobathy Lidar DEM: Puerto Rico",
        role=DatasetRole.DERIVED_DEM,
        provider="USACE / FEMA / NOAA OCM",
        landing_url="https://coast.noaa.gov/htdata/raster2/elevation/USACE_PR_Topobathy_DEM_2018_8571/",
        url_list_url="https://coast.noaa.gov/htdata/raster2/elevation/USACE_PR_Topobathy_DEM_2018_8571/urllist8571.txt",
        notes="1 m topobathy DEM distribution; use tile index for AOI subset before download.",
    ),
    MarineDatasetAnchor(
        dataset_id="9524",
        title="NCEI CUDEM Third Arc-Second Bathymetric-Topographic Tiles: Puerto Rico",
        role=DatasetRole.FUSED_COASTAL_DEM,
        provider="NOAA NCEI / NOAA OCM",
        landing_url="https://chs.coast.noaa.gov/htdata/raster5/elevation/NCEI_third_Topobathy_PuertoRico_9524/",
        url_list_url="https://chs.coast.noaa.gov/htdata/raster5/elevation/NCEI_third_Topobathy_PuertoRico_9524/urllist9524.txt",
        notes="Fused/generalized context product; never count as an independent sensor by itself.",
    ),
)


def dataset_by_id(dataset_id: str) -> MarineDatasetAnchor:
    matches = [item for item in PUERTO_RICO_MARINE_DATASETS if item.dataset_id == dataset_id]
    if len(matches) != 1:
        raise KeyError(dataset_id)
    return matches[0]
