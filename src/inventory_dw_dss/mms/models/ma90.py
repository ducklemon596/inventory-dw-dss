def forecast(row):
    """90 observed calendar days ending at T, inclusive; forecast is sales-based."""
    return {"vel90": row.vel90, "forecast_30d": 30 * row.vel90}
