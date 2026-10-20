# Postcode districts

`postcode_districts.csv` maps each Great Britain postcode district (outward code, e.g.
`SW1A`) to a centroid, an ONS region and an area name (Feature 02 §8, amendment A3). It
is the offline postcode lookup behind `app.modules.geo.districts`: the demo seed places
dealers on it, and Features 04 and 07 fall back to it when postcodes.io is unavailable.

## Source and licence

Derived from the **ONS Postcode Directory (ONSPD), August 2026 edition**, published by the
Office for National Statistics on the Open Geography Portal (ArcGIS item
`9e5a92a3cfb14dc7ad43d6ea7a7b8c7f`). Only the derived file is committed, never the
ONSPD itself.

The ONSPD is under the Open Government Licence v3.0, and the following attribution must
be displayed wherever this data is used (the site's attribution page, Feature 15):

> Contains OS data © Crown copyright and database right 2026
> Contains Royal Mail data © Royal Mail copyright and database right 2026
> Source: Office for National Statistics licensed under the Open Government Licence v.3.0

**Northern Ireland is excluded.** ONS distributes Northern Ireland postcodes (`BT`) under
a Land and Property Services end-user licence for internal business use only, so they
are not OGL and cannot be redistributed here. `region_for_postcode` maps any `BT` code to
Northern Ireland by rule (the `BT` area is exactly Northern Ireland); `district_for`
returns `None` for them, so NI locations need postcodes.io.

## Columns

| Column | Meaning |
|---|---|
| `outward_code` | The district, upper case, no space (`SW1A`, `M1`). |
| `latitude`, `longitude` | Median (not mean) WGS84 coordinate of the district's postcodes, 6 dp. |
| `region_code` | ONS region (`E12000001`–`E12000009`) or nation (`W92000004`, `S92000003`) holding most of the district's postcodes. |
| `area_name` | Name of the local authority holding most of the district's postcodes (`Westminster`). ONSPD has no post town: that is Royal Mail PAF data, licensed separately. |

Only live (not terminated), small-user postcodes with a grid reference count. Large-user
and PO Box postcodes are placed at the sorting office, so pseudo-districts made only of
them (`BS98`, `CR9`) are absent. That is about 2,740 districts.

## Rebuilding (each quarterly edition, or never: districts change slowly)

1. Download the latest "ONS Postcode Directory (<Month> <Year>)" zip from the
   [Open Geography Portal](https://geoportal.statistics.gov.uk/) (~250 MB). Do not
   extract it; the builder streams the CSV from inside the zip.
2. From `backend/`:

   ```sh
   uv run python -m scripts.build_postcode_districts --onspd PATH/ONSPD_<MON>_<YEAR>.zip
   ```

3. Update the edition, item id and attribution year above, run
   `uv run pytest tests/test_geo_districts.py`, and review the diff. The same edition
   always produces a byte-identical file.
