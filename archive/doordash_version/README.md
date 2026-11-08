# Archive: the DoorDash + Indian-data version (8 November 2026)

The second version of this case ran on a Kaggle release of DoorDash deliveries (6 US markets, 2015) plus an Indian food-delivery dataset for weather and batching. It was replaced because the DoorDash data has **no promised delivery time** (so "late" had to be an arbitrary 60-minute threshold), its dasher counts are local snapshots, and the Indian data looks partly synthetic.

This folder keeps its cleaning scripts and aggregated outputs. The complete version (SQL, model, simulator) is in the Git history at commit `547629b`. Nothing in the current pipeline reads these files.
