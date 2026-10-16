-- DB-03: allergens and intolerances (FR-P6, FR-N3). The 14 EU major allergens (Regulation 1169/2011)
-- plus lactose, which is an intolerance and common in Poland.
INSERT INTO allergen (name, description) VALUES
  ('gluten',      'Cereals containing gluten: wheat, rye, barley, oats'),
  ('crustaceans', 'Shrimp, crab, lobster'),
  ('eggs',        'Eggs and egg products'),
  ('fish',        'Fish and fish products'),
  ('peanuts',     'Peanuts and peanut products'),
  ('soy',         'Soybeans and soy products'),
  ('milk',        'Milk protein and dairy products'),
  ('lactose',     'Lactose intolerance: milk sugar in dairy products'),
  ('tree nuts',   'Almonds, hazelnuts, walnuts, cashews, pistachios and others'),
  ('celery',      'Celery and celeriac'),
  ('mustard',     'Mustard and mustard products'),
  ('sesame',      'Sesame seeds and sesame products'),
  ('sulphites',   'Sulphur dioxide and sulphites above 10 mg/kg'),
  ('lupin',       'Lupin seeds and flour'),
  ('molluscs',    'Mussels, oysters, squid, snails')
ON CONFLICT (name) DO UPDATE SET description = EXCLUDED.description;
