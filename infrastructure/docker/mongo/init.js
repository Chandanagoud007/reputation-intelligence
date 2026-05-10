db = db.getSiblingDB('reputation_reviews');

db.createCollection('reviews');
db.createCollection('raw_api_responses');

db.reviews.createIndex({ tenant_id: 1, created_at: -1 });
db.reviews.createIndex({ location_id: 1, source: 1 });
db.reviews.createIndex({ sentiment_score: 1 });

print('MongoDB initialized successfully');
