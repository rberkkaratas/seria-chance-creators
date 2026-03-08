"""
Creative Archetype Clustering
-------------------------------
Uses K-Means to group creative midfielders into distinct archetypes
based on their chance-creation profile.

Expected archetypes (will emerge from data):
    - "Final-Ball Specialists"  → high key passes, through balls, assists
    - "Progressive Carriers"    → high progressive carries, dribbles, ball progression
    - "Volume Creators"         → high touch count, pass volume, tempo control

Usage:
    python -m src.features.clustering
"""

import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans

import config


# ─── Archetype Labels ────────────────────────────────────────────────
# Map cluster IDs to human-readable names after inspecting centroids.
# Update these after your first run based on what the data shows.
ARCHETYPE_LABELS = {
    0: "Final-Ball Specialist",
    1: "Progressive Carrier",
    2: "Volume Creator",
}


def load_chance_creators() -> pd.DataFrame:
    """Load the feature-engineered dataset."""
    return pd.read_csv(config.DATA_FINAL / "chance_creators.csv")


def prepare_clustering_features(df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    """
    Select and scale features for clustering.

    Returns
    -------
    df : DataFrame (original, unmodified)
    X_scaled : ndarray of scaled features
    """
    features = [f for f in config.CLUSTERING_FEATURES if f in df.columns]

    if not features:
        raise ValueError(
            "No clustering features found in data. "
            "Check config.CLUSTERING_FEATURES against your columns."
        )

    X = df[features].fillna(0).values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    return df, X_scaled


def fit_clusters(X_scaled: np.ndarray) -> np.ndarray:
    """
    Run K-Means clustering.
    Returns cluster labels.
    """
    kmeans = KMeans(
        n_clusters=config.N_CLUSTERS,
        random_state=config.RANDOM_STATE,
        n_init=10,
    )
    labels = kmeans.fit_predict(X_scaled)
    return labels


def assign_archetype_labels(df: pd.DataFrame, labels: np.ndarray) -> pd.DataFrame:
    """
    Add cluster ID and human-readable archetype label to the DataFrame.

    IMPORTANT: After your first run, inspect the cluster centroids and
    update ARCHETYPE_LABELS at the top of this file to match what the
    data actually shows. The default labels are placeholders.
    """
    df = df.copy()
    df["cluster_id"] = labels
    df["archetype"] = df["cluster_id"].map(ARCHETYPE_LABELS)

    # If labels haven't been customized yet, use generic names
    df["archetype"] = df["archetype"].fillna(
        df["cluster_id"].apply(lambda x: f"Archetype {x + 1}")
    )

    return df


def print_cluster_summary(df: pd.DataFrame):
    """
    Print a summary of each cluster to help you assign meaningful labels.
    """
    features = [f for f in config.CLUSTERING_FEATURES if f in df.columns]

    for cid in sorted(df["cluster_id"].unique()):
        cluster = df[df["cluster_id"] == cid]
        label = cluster["archetype"].iloc[0]
        print(f"\n{'='*60}")
        print(f"Cluster {cid}: {label} ({len(cluster)} players)")
        print(f"{'='*60}")
        print(f"Key players: {', '.join(cluster.head(3)['player_name'].tolist())}")
        print(f"\nAverage metrics (per 90):")
        for feat in features:
            if feat in cluster.columns:
                print(f"  {feat:35s} {cluster[feat].mean():.2f}")


def run_clustering():
    """
    Full clustering pipeline.
    """
    print("Loading chance creators...")
    df = load_chance_creators()

    print(f"Preparing features for clustering ({config.N_CLUSTERS} clusters)...")
    df, X_scaled = prepare_clustering_features(df)

    print("Fitting K-Means...")
    labels = fit_clusters(X_scaled)

    print("Assigning archetype labels...")
    df = assign_archetype_labels(df, labels)

    print_cluster_summary(df)

    # Save
    output_path = config.DATA_FINAL / "chance_creators_clustered.csv"
    df.to_csv(output_path, index=False)
    print(f"\nSaved clustered data to {output_path}")


if __name__ == "__main__":
    run_clustering()
