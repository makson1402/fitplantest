-- DB-03: food categories (FR-P8). Proposed defaults, see docs/questions.md.
INSERT INTO food_category (name, description) VALUES
  ('poultry',             'Chicken, turkey and other poultry'),
  ('red meat',            'Beef, pork, lamb and cured meats'),
  ('fish and seafood',    'Fish, shellfish and seafood'),
  ('eggs',                'Eggs and egg dishes'),
  ('dairy',               'Milk, yoghurt, cheese and quark'),
  ('legumes',             'Beans, lentils, chickpeas, peas and soy products'),
  ('grains and cereals',  'Rice, pasta, oats, groats and other grains'),
  ('bread and bakery',    'Bread, rolls and baked goods'),
  ('vegetables',          'Fresh, cooked and frozen vegetables'),
  ('fruit',               'Fresh and dried fruit'),
  ('nuts and seeds',      'Nuts, seeds and nut butters'),
  ('fats and oils',       'Oils, butter and other added fats'),
  ('sweets and snacks',   'Sweets, desserts and savoury snacks'),
  ('prepared dishes',     'Composite dishes, for example pizza or sushi (photo recognition labels)'),
  ('plant-based protein', 'Tofu, tempeh, seitan and plant-based substitutes'),
  ('beverages',           'Drinks with calories: juices, milk drinks, sports drinks')
ON CONFLICT (name) DO UPDATE SET description = EXCLUDED.description;
