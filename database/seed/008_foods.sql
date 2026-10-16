-- DB-05: foods (FR-P6, FR-P8, FR-N2, FR-N3). Values are per 100 g.
--
-- SOURCE AND TRUST: base foods (everything not tagged as a dish) follow USDA FoodData Central / SR Legacy values,
-- rounded; dish rows (role 'dish') are typical restaurant/recipe averages (USDA and common recipes). ALL VALUES WERE
-- ENTERED FROM MEMORY AND MUST BE SPOT-CHECKED against FoodData Central before release (see docs/questions.md).
-- Allergens of dishes are best-effort from typical recipes; a human must review them (safety relevant, FR-N3).
--
-- Columns: name, kcal, protein, fat, carbs, role, meals (b=breakfast l=lunch d=dinner s=snack), vegetarian, vegan,
-- default/min/max portion g, portion step g, Food-101 recognition_label (NULL = not recognisable),
-- categories (comma list of food_category.name), allergens (comma list of allergen.name).
-- Idempotent: natural key = name. Unknown categories, allergens or roles abort the load.
DROP TABLE IF EXISTS _food_seed;
CREATE TEMP TABLE _food_seed (
  name text, kcal numeric, protein numeric, fat numeric, carbs numeric, role text, meals text,
  vegetarian boolean, vegan boolean, def_g int, min_g int, max_g int, step_g int,
  label text, cats text, allergens text
);
INSERT INTO _food_seed VALUES
-- ------------------------------------------------------------------ meat and poultry (protein)
('Chicken breast, cooked',165,31,3.6,0,'protein','l,d',false,false,120,60,300,5,NULL,'poultry',''),
('Chicken thigh, cooked, skinless',209,26,10.9,0,'protein','l,d',false,false,120,60,300,5,NULL,'poultry',''),
('Turkey breast, cooked',135,30,0.7,0,'protein','l,d',false,false,120,60,300,5,NULL,'poultry',''),
('Beef, lean (sirloin), cooked',190,29,8,0,'protein','l,d',false,false,120,60,300,5,'steak','red meat',''),
('Beef mince 10% fat, cooked',217,26,12,0,'protein','l,d',false,false,120,60,300,5,NULL,'red meat',''),
('Pork tenderloin, cooked',143,26,3.5,0,'protein','l,d',false,false,120,60,300,5,NULL,'red meat',''),
('Pork loin chop, cooked',200,27,9.5,0,'protein','l,d',false,false,120,60,300,5,'pork_chop','red meat',''),
('Ham, lean',120,18,4.5,1.5,'protein','b,l,d',false,false,60,30,200,5,NULL,'red meat',''),
-- ------------------------------------------------------------------ fish and seafood (protein)
('Salmon, cooked',206,22,12,0,'protein','l,d',false,false,120,60,300,5,'grilled_salmon','fish and seafood','fish'),
('Cod, cooked',105,23,0.9,0,'protein','l,d',false,false,150,60,300,5,NULL,'fish and seafood','fish'),
('Tuna, canned in water',116,26,1,0,'protein','b,l,d,s',false,false,80,40,200,5,NULL,'fish and seafood','fish'),
('Mackerel, cooked',262,24,18,0,'protein','l,d',false,false,100,60,250,5,NULL,'fish and seafood','fish'),
('Trout, cooked',168,24,7.5,0,'protein','l,d',false,false,120,60,300,5,NULL,'fish and seafood','fish'),
('Sardines, canned in oil',208,24.6,11.5,0,'protein','b,l,d',false,false,80,40,200,5,NULL,'fish and seafood','fish'),
('Smoked salmon',117,18,4.3,0,'protein','b,l',false,false,60,30,150,5,NULL,'fish and seafood','fish'),
('Shrimp, cooked',99,24,0.3,0.2,'protein','l,d',false,false,100,50,250,5,NULL,'fish and seafood','crustaceans'),
-- ------------------------------------------------------------------ eggs, plant proteins, legumes
('Egg, whole, boiled',155,13,11,1.1,'protein','b,l,d',true,false,100,50,250,50,NULL,'eggs','eggs'),
('Egg white',52,11,0.2,0.7,'protein','b,l,d',true,false,100,50,250,10,NULL,'eggs','eggs'),
('Tofu, firm',144,17,8.7,2.8,'protein','b,l,d',true,true,120,60,300,10,NULL,'plant-based protein','soy'),
('Tempeh',192,20,11,7.6,'protein','l,d',true,true,100,50,250,10,NULL,'plant-based protein','soy'),
('Seitan',143,25,1.9,6,'protein','l,d',true,true,100,50,250,10,NULL,'plant-based protein','gluten'),
('Lentils, cooked',116,9,0.4,20,'protein','l,d',true,true,150,60,350,10,NULL,'legumes',''),
('Chickpeas, cooked',164,8.9,2.6,27.4,'protein','l,d',true,true,150,60,350,10,NULL,'legumes',''),
('Kidney beans, cooked',127,8.7,0.5,22.8,'protein','l,d',true,true,150,60,350,10,NULL,'legumes',''),
('Edamame',121,11.9,5.2,8.9,'protein','l,d,s',true,true,100,50,250,10,'edamame','legumes','soy'),
('Lupin beans, cooked',119,15.6,2.9,9.9,'protein','l,d',true,true,100,50,250,10,NULL,'legumes','lupin'),
('Whey protein powder',380,80,6,7,'protein','b,s',true,false,30,15,60,5,NULL,'dairy','milk,lactose'),
-- ------------------------------------------------------------------ dairy
('Cottage cheese',98,11.1,4.3,3.4,'dairy','b,l,d,s',true,false,150,50,300,10,NULL,'dairy','milk,lactose'),
('Skyr, natural',63,11,0.2,4,'dairy','b,s',true,false,150,50,400,10,NULL,'dairy','milk,lactose'),
('Greek yogurt 2%',73,9.9,1.9,3.9,'dairy','b,s',true,false,150,50,400,10,NULL,'dairy','milk,lactose'),
('Natural yogurt 3%',62,3.5,3.3,4.7,'dairy','b,s',true,false,150,50,400,10,NULL,'dairy','milk,lactose'),
('Milk 2%',50,3.4,2,4.9,'dairy','b,s',true,false,250,100,500,50,NULL,'dairy,beverages','milk,lactose'),
('Kefir',41,3.4,1,4.7,'dairy','b,s',true,false,250,100,500,50,NULL,'dairy,beverages','milk,lactose'),
('Quark, semi-fat (twarog polotlusty)',133,18,4,3.5,'dairy','b,l,d,s',true,false,150,50,300,10,NULL,'dairy','milk,lactose'),
('Mozzarella, part-skim',254,24.3,15.9,2.8,'dairy','b,l,d,s',true,false,60,30,150,5,NULL,'dairy','milk'),
('Cheddar',403,25,33,1.3,'dairy','b,l,d,s',true,false,30,15,100,5,NULL,'dairy','milk'),
('Feta',264,14,21,4,'dairy','b,l,d,s',true,false,40,20,100,5,NULL,'dairy','milk,lactose'),
('Cream 18% (smietana)',186,2.5,18,3.5,'dairy','l,d',true,false,30,15,100,5,NULL,'dairy','milk,lactose'),
('Soy yogurt, plain',52,4,2.5,3.5,'dairy','b,s',true,true,150,50,400,10,NULL,'dairy,plant-based protein','soy'),
('Soy milk, unsweetened',33,2.9,1.6,1.7,'dairy','b,s',true,true,250,100,500,50,NULL,'beverages,plant-based protein','soy'),
-- ------------------------------------------------------------------ grains, bread, potatoes (carb)
('White rice, cooked',130,2.7,0.3,28.2,'carb','l,d',true,true,150,50,450,10,NULL,'grains and cereals',''),
('Brown rice, cooked',112,2.3,0.8,23.5,'carb','l,d',true,true,150,50,450,10,NULL,'grains and cereals',''),
('Pasta, cooked',158,5.8,0.9,30.9,'carb','l,d',true,true,150,50,450,10,NULL,'grains and cereals','gluten'),
('Whole-wheat pasta, cooked',124,5.3,0.5,26.5,'carb','l,d',true,true,150,50,450,10,NULL,'grains and cereals','gluten'),
('Buckwheat groats, cooked (kasza gryczana)',92,3.4,0.6,19.9,'carb','l,d',true,true,150,50,450,10,NULL,'grains and cereals',''),
('Pearl barley, cooked (kasza jeczmienna)',123,2.3,0.4,28.2,'carb','l,d',true,true,150,50,450,10,NULL,'grains and cereals','gluten'),
('Millet, cooked (kasza jaglana)',119,3.5,1,23.7,'carb','l,d',true,true,150,50,450,10,NULL,'grains and cereals',''),
('Quinoa, cooked',120,4.4,1.9,21.3,'carb','l,d',true,true,150,50,450,10,NULL,'grains and cereals',''),
('Couscous, cooked',112,3.8,0.2,23.2,'carb','l,d',true,true,150,50,450,10,NULL,'grains and cereals','gluten'),
('Bulgur, cooked',83,3.1,0.2,18.6,'carb','l,d',true,true,150,50,450,10,NULL,'grains and cereals','gluten'),
('Rice noodles, cooked',108,0.9,0.2,24.9,'carb','l,d',true,true,150,50,400,10,NULL,'grains and cereals',''),
('Oats, rolled, dry',379,13.2,6.5,67.7,'carb','b',true,true,50,20,120,5,NULL,'grains and cereals','gluten'),
('Muesli, no added sugar',362,10,6,66,'carb','b',true,true,50,20,120,5,NULL,'grains and cereals','gluten'),
('Corn flakes',357,7.5,0.4,84,'carb','b',true,true,40,20,100,5,NULL,'grains and cereals','gluten'),
('Rice cakes',387,8.2,2.8,81.5,'carb','b,s',true,true,20,10,60,10,NULL,'grains and cereals',''),
('Rye bread, whole grain',259,8.5,3.3,48.3,'carb','b,l,d,s',true,true,60,30,200,30,NULL,'bread and bakery','gluten'),
('Whole-wheat bread',247,13,3.4,41,'carb','b,l,d,s',true,true,60,30,200,30,NULL,'bread and bakery','gluten'),
('White bread roll (bulka)',266,9,3.2,49,'carb','b,l,d,s',true,true,60,30,200,30,NULL,'bread and bakery','gluten'),
('Wheat tortilla',306,8.6,7.6,51,'carb','b,l,d',true,true,60,30,180,30,NULL,'bread and bakery','gluten'),
('Potato, boiled',87,1.9,0.1,20.1,'carb','l,d',true,true,200,80,500,10,NULL,'vegetables',''),
('Sweet potato, baked',90,2,0.2,20.7,'carb','l,d',true,true,200,80,500,10,NULL,'vegetables',''),
-- ------------------------------------------------------------------ fats and oils, nuts, seeds
('Olive oil',884,0,100,0,'fat','b,l,d',true,true,10,5,30,5,NULL,'fats and oils',''),
('Rapeseed oil',884,0,100,0,'fat','b,l,d',true,true,10,5,30,5,NULL,'fats and oils',''),
('Butter',717,0.9,81,0.1,'fat','b,l,d',true,false,10,5,30,5,NULL,'fats and oils,dairy','milk'),
('Avocado',160,2,14.7,8.5,'fat','b,l,d,s',true,true,70,30,200,10,NULL,'fruit,fats and oils',''),
('Almonds',579,21.2,49.9,21.6,'fat','b,l,d,s',true,true,30,10,80,5,NULL,'nuts and seeds','tree nuts'),
('Walnuts',654,15.2,65.2,13.7,'fat','b,l,d,s',true,true,30,10,80,5,NULL,'nuts and seeds','tree nuts'),
('Cashews',553,18.2,43.9,30.2,'fat','b,l,d,s',true,true,30,10,80,5,NULL,'nuts and seeds','tree nuts'),
('Hazelnuts',628,15,60.8,16.7,'fat','b,l,d,s',true,true,30,10,80,5,NULL,'nuts and seeds','tree nuts'),
('Peanuts',567,25.8,49.2,16.1,'fat','b,l,d,s',true,true,30,10,80,5,NULL,'nuts and seeds','peanuts'),
('Peanut butter',588,25,50,20,'fat','b,l,d,s',true,true,20,10,60,5,NULL,'nuts and seeds','peanuts'),
('Sunflower seeds',584,20.8,51.5,20,'fat','b,l,d,s',true,true,20,10,60,5,NULL,'nuts and seeds',''),
('Pumpkin seeds',559,30.2,49,10.7,'fat','b,l,d,s',true,true,20,10,60,5,NULL,'nuts and seeds',''),
('Chia seeds',486,16.5,30.7,42.1,'fat','b,s',true,true,15,5,40,5,NULL,'nuts and seeds',''),
('Flaxseed',534,18.3,42.2,28.9,'fat','b,s',true,true,15,5,40,5,NULL,'nuts and seeds',''),
('Sesame seeds',573,17.7,49.7,23.5,'fat','b,l,d,s',true,true,10,5,30,5,NULL,'nuts and seeds','sesame'),
('Tahini',595,17,53.8,21.2,'fat','b,l,d',true,true,15,5,40,5,NULL,'nuts and seeds','sesame'),
-- ------------------------------------------------------------------ vegetables
('Broccoli, cooked',35,2.4,0.4,7.2,'vegetable','l,d',true,true,150,50,300,10,NULL,'vegetables',''),
('Spinach, raw',23,2.9,0.4,3.6,'vegetable','b,l,d',true,true,100,50,300,10,NULL,'vegetables',''),
('Tomato, raw',18,0.9,0.2,3.9,'vegetable','b,l,d',true,true,120,50,300,10,NULL,'vegetables',''),
('Cucumber, raw',15,0.7,0.1,3.6,'vegetable','b,l,d',true,true,120,50,300,10,NULL,'vegetables',''),
('Bell pepper, red, raw',31,1,0.3,6,'vegetable','b,l,d',true,true,120,50,300,10,NULL,'vegetables',''),
('Carrot, raw',41,0.9,0.2,9.6,'vegetable','l,d,s',true,true,100,50,300,10,NULL,'vegetables',''),
('Onion, raw',40,1.1,0.1,9.3,'vegetable','l,d',true,true,60,30,200,10,NULL,'vegetables',''),
('Zucchini, cooked',17,1.2,0.3,3.1,'vegetable','l,d',true,true,150,50,300,10,NULL,'vegetables',''),
('Cauliflower, cooked',23,1.8,0.5,4.1,'vegetable','l,d',true,true,150,50,300,10,NULL,'vegetables',''),
('White cabbage, raw',25,1.3,0.1,5.8,'vegetable','l,d',true,true,120,50,300,10,NULL,'vegetables',''),
('Lettuce',15,1.4,0.2,2.9,'vegetable','l,d',true,true,80,30,200,10,NULL,'vegetables',''),
('Mushrooms, raw (pieczarki)',22,3.1,0.3,3.3,'vegetable','b,l,d',true,true,100,50,250,10,NULL,'vegetables',''),
('Green beans, cooked',35,1.9,0.3,7.9,'vegetable','l,d',true,true,150,50,300,10,NULL,'vegetables',''),
('Asparagus, cooked',22,2.4,0.2,4.1,'vegetable','l,d',true,true,120,50,300,10,NULL,'vegetables',''),
('Green peas, cooked',84,5.4,0.2,15.6,'vegetable','l,d',true,true,100,50,250,10,NULL,'vegetables',''),
('Beetroot, cooked',44,1.7,0.2,10,'vegetable','l,d',true,true,100,50,250,10,NULL,'vegetables',''),
('Celery stalk, raw',14,0.7,0.2,3,'vegetable','l,d,s',true,true,80,30,200,10,NULL,'vegetables','celery'),
('Celeriac, raw',42,1.5,0.3,9.2,'vegetable','l,d',true,true,100,50,250,10,NULL,'vegetables','celery'),
('Kale, raw',49,4.3,0.9,8.8,'vegetable','l,d',true,true,80,30,200,10,NULL,'vegetables',''),
('Pumpkin, cooked',20,0.7,0.1,4.9,'vegetable','l,d',true,true,150,50,300,10,NULL,'vegetables',''),
('Eggplant, cooked',35,0.8,0.2,8.7,'vegetable','l,d',true,true,150,50,300,10,NULL,'vegetables',''),
('Leek, raw',61,1.5,0.3,14.2,'vegetable','l,d',true,true,80,30,200,10,NULL,'vegetables',''),
('Sauerkraut (kapusta kiszona)',19,0.9,0.1,4.3,'vegetable','l,d',true,true,100,50,250,10,NULL,'vegetables',''),
('Pickled cucumber (ogorek kiszony)',11,0.3,0.2,2.3,'vegetable','b,l,d',true,true,80,30,200,10,NULL,'vegetables',''),
('Radish',16,0.7,0.1,3.4,'vegetable','b,l,d',true,true,60,30,150,10,NULL,'vegetables',''),
('Brussels sprouts, cooked',36,2.6,0.5,7.1,'vegetable','l,d',true,true,120,50,300,10,NULL,'vegetables',''),
-- ------------------------------------------------------------------ fruit
('Banana',89,1.1,0.3,22.8,'fruit','b,s',true,true,120,50,300,10,NULL,'fruit',''),
('Apple',52,0.3,0.2,13.8,'fruit','b,s',true,true,150,50,300,10,NULL,'fruit',''),
('Orange',47,0.9,0.1,11.8,'fruit','b,s',true,true,150,50,300,10,NULL,'fruit',''),
('Strawberries',32,0.7,0.3,7.7,'fruit','b,s',true,true,150,50,300,10,NULL,'fruit',''),
('Blueberries',57,0.7,0.3,14.5,'fruit','b,s',true,true,100,50,300,10,NULL,'fruit',''),
('Raspberries',52,1.2,0.7,11.9,'fruit','b,s',true,true,100,50,300,10,NULL,'fruit',''),
('Grapes',69,0.7,0.2,18.1,'fruit','b,s',true,true,100,50,300,10,NULL,'fruit',''),
('Pear',57,0.4,0.1,15.2,'fruit','b,s',true,true,150,50,300,10,NULL,'fruit',''),
('Peach',39,0.9,0.3,9.5,'fruit','b,s',true,true,150,50,300,10,NULL,'fruit',''),
('Kiwi',61,1.1,0.5,14.7,'fruit','b,s',true,true,100,50,300,10,NULL,'fruit',''),
('Pineapple',50,0.5,0.1,13.1,'fruit','b,s',true,true,120,50,300,10,NULL,'fruit',''),
('Mango',60,0.8,0.4,15,'fruit','b,s',true,true,120,50,300,10,NULL,'fruit',''),
('Watermelon',30,0.6,0.2,7.6,'fruit','s',true,true,200,80,500,10,NULL,'fruit',''),
('Plum',46,0.7,0.3,11.4,'fruit','b,s',true,true,100,50,300,10,NULL,'fruit',''),
('Grapefruit',42,0.8,0.1,10.7,'fruit','b,s',true,true,150,50,300,10,NULL,'fruit',''),
('Cherries',63,1.1,0.2,16,'fruit','b,s',true,true,100,50,300,10,NULL,'fruit',''),
('Dried apricots (sulphured)',241,3.4,0.5,62.6,'fruit','b,s',true,true,30,15,80,5,NULL,'fruit','sulphites'),
('Dates, dried',282,2.5,0.4,75,'fruit','b,s',true,true,30,15,80,5,NULL,'fruit',''),
-- ------------------------------------------------------------------ other (sweeteners, sauces, snacks)
('Honey',304,0.3,0,82.4,'other','b,s',true,false,15,5,40,5,NULL,'sweets and snacks',''),
('Dark chocolate 70%',598,7.8,42.6,45.9,'other','s',true,false,20,10,50,5,NULL,'sweets and snacks',''),
('Hummus',166,7.9,9.6,14.3,'other','b,l,d,s',true,true,60,30,150,10,'hummus','legumes,prepared dishes','sesame'),
('Soy sauce',53,8.1,0.6,4.9,'other','l,d',true,true,15,5,30,5,NULL,'prepared dishes','soy,gluten'),
('Mustard',60,3.7,3.3,5.8,'other','b,l,d',true,true,10,5,30,5,NULL,'prepared dishes','mustard'),
-- ------------------------------------------------------------------ dishes (Food-101 recognition labels; estimates)
('Omelette',154,11,12,0.6,'dish','b,l',true,false,200,100,400,25,'omelette','eggs,prepared dishes','eggs,milk'),
('Scrambled eggs',148,10,11,1.6,'dish','b',true,false,150,100,350,25,NULL,'eggs,prepared dishes','eggs,milk'),
('Pizza',266,11,10,33,'dish','l,d',true,false,250,100,500,25,'pizza','prepared dishes','gluten,milk'),
('Hamburger',250,13,12,22,'dish','l,d',false,false,200,100,400,25,'hamburger','prepared dishes','gluten,sesame,mustard'),
('Hot dog',250,10,15,18,'dish','l,d',false,false,150,80,300,25,'hot_dog','prepared dishes','gluten,mustard'),
('French fries',312,3.4,15,41,'dish','l,d,s',true,true,150,80,350,25,'french_fries','prepared dishes',''),
('Pancakes',227,6,9,31,'dish','b',true,false,200,100,400,25,'pancakes','prepared dishes','gluten,eggs,milk'),
('Waffles',291,7.9,14,35,'dish','b',true,false,150,80,300,25,'waffles','prepared dishes','gluten,eggs,milk'),
('French toast',229,7.9,12,24,'dish','b',true,false,150,80,300,25,'french_toast','prepared dishes','gluten,eggs,milk'),
('Spaghetti bolognese',150,8,5,18,'dish','l,d',false,false,300,150,600,25,'spaghetti_bolognese','prepared dishes','gluten,celery'),
('Spaghetti carbonara',200,8,9,22,'dish','l,d',false,false,300,150,600,25,'spaghetti_carbonara','prepared dishes','gluten,eggs,milk'),
('Lasagna',135,8,6,12,'dish','l,d',false,false,300,150,500,25,'lasagna','prepared dishes','gluten,milk,eggs'),
('Macaroni and cheese',170,7,8,18,'dish','l,d',true,false,250,120,500,25,'macaroni_and_cheese','prepared dishes','gluten,milk'),
('Risotto',150,4,5,22,'dish','l,d',true,false,300,150,500,25,'risotto','prepared dishes','milk,celery'),
('Ravioli',184,7.5,6,25,'dish','l,d',true,false,250,120,500,25,'ravioli','prepared dishes','gluten,eggs,milk'),
('Gnocchi',151,3.5,1.5,31,'dish','l,d',true,false,250,120,500,25,'gnocchi','prepared dishes','gluten,eggs'),
('Dumplings (pierogi)',189,6,5,30,'dish','l,d',true,false,250,120,500,25,'dumplings','prepared dishes','gluten,eggs,milk'),
('Fried rice',160,4.5,5.5,23,'dish','l,d',true,false,300,150,500,25,'fried_rice','prepared dishes','eggs,soy,sesame'),
('Pad thai',174,8,6,22,'dish','l,d',false,false,300,150,500,25,'pad_thai','prepared dishes','peanuts,eggs,fish,soy,crustaceans'),
('Paella',145,8,4.5,18,'dish','l,d',false,false,300,150,500,25,'paella','prepared dishes','crustaceans,molluscs,fish'),
('Sushi',148,5.5,1.5,28,'dish','l,d',false,false,200,100,400,25,'sushi','prepared dishes','fish,soy,sesame'),
('Sashimi',125,20,5,0,'dish','l,d',false,false,120,60,300,10,'sashimi','fish and seafood,prepared dishes','fish'),
('Ramen',95,5,3.5,11,'dish','l,d',false,false,400,250,700,50,'ramen','prepared dishes','gluten,eggs,soy'),
('Pho',62,5,1.5,7,'dish','l,d',false,false,400,250,700,50,'pho','prepared dishes','soy,fish'),
('Miso soup',41,3,1.5,4,'dish','l,d,s',true,true,250,150,400,25,'miso_soup','prepared dishes','soy'),
('Hot and sour soup',41,2.5,1.5,4.5,'dish','l,d',false,false,300,200,500,25,'hot_and_sour_soup','prepared dishes','eggs,soy,gluten'),
('French onion soup',50,2.5,2,5.5,'dish','l,d',false,false,300,200,500,25,'french_onion_soup','prepared dishes','gluten,milk'),
('Clam chowder',92,4,4.5,9,'dish','l,d',false,false,300,200,500,25,'clam_chowder','prepared dishes','molluscs,milk,gluten'),
('Lobster bisque',92,3.5,5.5,7,'dish','l,d',false,false,300,200,500,25,'lobster_bisque','prepared dishes','crustaceans,milk,celery'),
('Falafel',333,13.3,17.8,31.8,'dish','l,d,s',true,true,100,50,250,25,'falafel','prepared dishes,legumes','sesame'),
('Tacos',210,10,10,20,'dish','l,d',false,false,200,100,400,25,'tacos','prepared dishes','milk'),
('Nachos',337,8,17,38,'dish','s,l',true,false,150,80,300,25,'nachos','prepared dishes,sweets and snacks','milk'),
('Chicken quesadilla',261,15,13,21,'dish','l,d',false,false,200,100,400,25,'chicken_quesadilla','prepared dishes','gluten,milk'),
('Breakfast burrito',210,10,10,20,'dish','b,l',false,false,200,100,400,25,'breakfast_burrito','prepared dishes','gluten,eggs,milk'),
('Huevos rancheros',152,8,8,12,'dish','b,l',true,false,250,150,450,25,'huevos_rancheros','prepared dishes,eggs','eggs,gluten'),
('Eggs benedict',219,10,15,11,'dish','b',false,false,200,100,350,25,'eggs_benedict','prepared dishes,eggs','eggs,gluten,milk'),
('Deviled eggs',188,9.5,16,1.5,'dish','s,l',true,false,100,50,250,25,'deviled_eggs','eggs,prepared dishes','eggs,mustard'),
('Club sandwich',239,14,11,21,'dish','l,d',false,false,250,120,450,25,'club_sandwich','prepared dishes','gluten,eggs,mustard'),
('Grilled cheese sandwich',332,14,20,24,'dish','l,d,b',true,false,150,80,300,25,'grilled_cheese_sandwich','prepared dishes','gluten,milk'),
('Pulled pork sandwich',241,16,9,24,'dish','l,d',false,false,220,120,400,25,'pulled_pork_sandwich','prepared dishes','gluten'),
('Lobster roll sandwich',244,14,12,20,'dish','l,d',false,false,200,100,350,25,'lobster_roll_sandwich','prepared dishes','crustaceans,gluten,eggs'),
('Bruschetta',191,5,7,27,'dish','s,l',true,true,120,60,300,25,'bruschetta','prepared dishes','gluten'),
('Garlic bread',344,8,16,42,'dish','s,l,d',true,false,80,40,200,20,'garlic_bread','bread and bakery,prepared dishes','gluten,milk'),
('Caesar salad',129,6,9,6,'dish','l,d',false,false,250,150,450,25,'caesar_salad','prepared dishes,vegetables','fish,eggs,milk,gluten,mustard'),
('Greek salad',113,3,9,5,'dish','l,d',true,false,250,150,450,25,'greek_salad','prepared dishes,vegetables','milk'),
('Caprese salad',156,8,12,4,'dish','l,d,s',true,false,200,100,400,25,'caprese_salad','prepared dishes,vegetables','milk'),
('Beet salad',84,2,4,10,'dish','l,d',true,true,200,100,400,25,'beet_salad','prepared dishes,vegetables',''),
('Seaweed salad',100,2,4,14,'dish','l,d,s',true,true,100,50,250,25,'seaweed_salad','prepared dishes,vegetables','soy,sesame'),
('Guacamole',168,2,14,8.5,'dish','s,l',true,true,60,30,150,10,'guacamole','prepared dishes,fruit',''),
('Spring rolls',218,5,10,27,'dish','s,l,d',true,false,120,60,300,20,'spring_rolls','prepared dishes','gluten,soy'),
('Gyoza',200,8,8,24,'dish','l,d,s',false,false,150,80,350,25,'gyoza','prepared dishes','gluten,soy,sesame'),
('Samosa',261,4.7,14,29,'dish','s,l',true,false,100,50,250,25,'samosa','prepared dishes','gluten'),
('Chicken curry',127,11,7,5,'dish','l,d',false,false,300,150,500,25,'chicken_curry','prepared dishes','milk'),
('Chicken wings',283,27,19,0,'dish','l,d,s',false,false,150,80,350,25,'chicken_wings','poultry,prepared dishes',''),
('Baby back ribs',286,22,22,0,'dish','l,d',false,false,250,120,450,25,'baby_back_ribs','red meat,prepared dishes',''),
('Prime rib',285,24,21,0,'dish','l,d',false,false,200,100,400,25,'prime_rib','red meat,prepared dishes',''),
('Filet mignon',212,26,12,0,'dish','l,d',false,false,180,100,350,25,'filet_mignon','red meat,prepared dishes',''),
('Fish and chips',231,10,11,23,'dish','l,d',false,false,300,150,500,25,'fish_and_chips','prepared dishes','fish,gluten'),
('Fried calamari',160,15,7.5,8,'dish','l,d,s',false,false,150,80,300,25,'fried_calamari','prepared dishes','molluscs,gluten,eggs'),
('Crab cakes',196,14,12,8,'dish','l,d',false,false,150,80,300,25,'crab_cakes','prepared dishes','crustaceans,eggs,gluten'),
('Mussels, cooked',166,24,4.5,7.4,'dish','l,d',false,false,200,100,400,25,'mussels','fish and seafood,prepared dishes','molluscs'),
('Oysters',66,7,2.5,3.9,'dish','l,d',false,false,100,50,250,25,'oysters','fish and seafood,prepared dishes','molluscs'),
('Scallops, cooked',111,20.5,0.8,5.4,'dish','l,d',false,false,120,60,250,10,'scallops','fish and seafood,prepared dishes','molluscs'),
('Ceviche',97,15,1.5,6,'dish','l,d',false,false,200,100,350,25,'ceviche','fish and seafood,prepared dishes','fish'),
('Tuna tartare',128,22,4,1,'dish','l,d',false,false,120,60,250,10,'tuna_tartare','fish and seafood,prepared dishes','fish,soy,sesame'),
('Takoyaki',184,7,8,21,'dish','s,l',false,false,150,80,300,25,'takoyaki','prepared dishes','gluten,eggs,molluscs,fish'),
('Shrimp and grits',138,9,6,12,'dish','l,d',false,false,300,150,500,25,'shrimp_and_grits','prepared dishes','crustaceans,milk'),
('Escargots',85,16,1.4,2,'dish','l,d',false,false,80,50,200,10,'escargots','prepared dishes','molluscs,milk'),
('Peking duck',328,19,28,0,'dish','l,d',false,false,150,80,300,25,'peking_duck','prepared dishes','soy,gluten'),
('Cheese plate',357,22,29,2,'dish','s,l,d',true,false,80,40,200,10,'cheese_plate','dairy,prepared dishes','milk,lactose'),
-- desserts and sweets
('Ice cream',209,3.5,11,24,'dish','s',true,false,100,50,250,25,'ice_cream','sweets and snacks','milk,eggs,lactose'),
('Frozen yogurt',127,3,4,22,'dish','s',true,false,100,50,250,25,'frozen_yogurt','sweets and snacks','milk,lactose'),
('Cheesecake',326,5.5,22.5,25.5,'dish','s',true,false,100,60,200,25,'cheesecake','sweets and snacks','milk,eggs,gluten'),
('Chocolate cake',376,5,16,53,'dish','s',true,false,100,60,200,25,'chocolate_cake','sweets and snacks','gluten,eggs,milk'),
('Apple pie',242,1.9,11,34,'dish','s',true,false,125,60,250,25,'apple_pie','sweets and snacks','gluten'),
('Carrot cake',413,4,21,52,'dish','s',true,false,100,60,200,25,'carrot_cake','sweets and snacks','gluten,eggs,milk,tree nuts'),
('Tiramisu',280,5.5,14,33,'dish','s',true,false,120,60,250,25,'tiramisu','sweets and snacks','gluten,eggs,milk'),
('Donuts',423,5,23,49,'dish','s',true,false,70,40,200,10,'donuts','sweets and snacks','gluten,eggs,milk'),
('Cup cakes',385,4,17,54,'dish','s',true,false,70,40,200,10,'cup_cakes','sweets and snacks','gluten,eggs,milk'),
('Macarons',421,7,17,60,'dish','s',true,false,30,15,100,10,'macarons','sweets and snacks','tree nuts,eggs'),
('Baklava',437,6,25,47,'dish','s',true,false,60,30,150,10,'baklava','sweets and snacks','gluten,tree nuts'),
('Churros',437,5,25,48,'dish','s',true,false,80,40,200,10,'churros','sweets and snacks','gluten'),
('Creme brulee',280,3.5,22,17,'dish','s',true,false,120,60,200,20,'creme_brulee','sweets and snacks','milk,eggs'),
('Panna cotta',242,3,18,17,'dish','s',true,false,120,60,200,20,'panna_cotta','sweets and snacks','milk');

DO $$
DECLARE missing text;
BEGIN
  SELECT string_agg(DISTINCT c, ', ') INTO missing FROM (
    SELECT btrim(unnest(string_to_array(cats, ','))) AS c FROM _food_seed) x
   WHERE c <> '' AND NOT EXISTS (SELECT 1 FROM food_category fc WHERE fc.name = x.c);
  IF missing IS NOT NULL THEN RAISE EXCEPTION 'food seed references unknown categories: %', missing; END IF;
  SELECT string_agg(DISTINCT a, ', ') INTO missing FROM (
    SELECT btrim(unnest(string_to_array(allergens, ','))) AS a FROM _food_seed) x
   WHERE a <> '' AND NOT EXISTS (SELECT 1 FROM allergen al WHERE al.name = x.a);
  IF missing IS NOT NULL THEN RAISE EXCEPTION 'food seed references unknown allergens: %', missing; END IF;
END $$;

INSERT INTO food_item (name, calories_per_100g, protein_per_100g, fat_per_100g, carbs_per_100g, role, suitable_meal_types,
                       is_vegetarian, is_vegan, default_portion_g, min_portion_g, max_portion_g, portion_step_g,
                       recognition_label, is_active)
SELECT s.name, s.kcal, s.protein, s.fat, s.carbs, s.role::food_role_t,
       ARRAY(SELECT (CASE btrim(m) WHEN 'b' THEN 'breakfast' WHEN 'l' THEN 'lunch' WHEN 'd' THEN 'dinner'
                                   WHEN 's' THEN 'snack' END)::meal_type_t
               FROM unnest(string_to_array(s.meals, ',')) AS m),
       s.vegetarian, s.vegan, s.def_g, s.min_g, s.max_g, s.step_g, s.label, true
  FROM _food_seed s
ON CONFLICT (name) DO UPDATE SET
  calories_per_100g = EXCLUDED.calories_per_100g, protein_per_100g = EXCLUDED.protein_per_100g,
  fat_per_100g = EXCLUDED.fat_per_100g, carbs_per_100g = EXCLUDED.carbs_per_100g, role = EXCLUDED.role,
  suitable_meal_types = EXCLUDED.suitable_meal_types, is_vegetarian = EXCLUDED.is_vegetarian,
  is_vegan = EXCLUDED.is_vegan, default_portion_g = EXCLUDED.default_portion_g,
  min_portion_g = EXCLUDED.min_portion_g, max_portion_g = EXCLUDED.max_portion_g,
  portion_step_g = EXCLUDED.portion_step_g, recognition_label = EXCLUDED.recognition_label;

-- The seed owns the category and allergen links of the foods it lists.
DELETE FROM food_category_food_item WHERE food_item_id IN (SELECT fi.id FROM food_item fi JOIN _food_seed s ON s.name = fi.name);
DELETE FROM food_item_allergen WHERE food_item_id IN (SELECT fi.id FROM food_item fi JOIN _food_seed s ON s.name = fi.name);

INSERT INTO food_category_food_item (food_category_id, food_item_id)
SELECT DISTINCT fc.id, fi.id
  FROM _food_seed s
  JOIN food_item fi ON fi.name = s.name
  JOIN LATERAL unnest(string_to_array(s.cats, ',')) AS c ON true
  JOIN food_category fc ON fc.name = btrim(c);

INSERT INTO food_item_allergen (food_item_id, allergen_id)
SELECT DISTINCT fi.id, al.id
  FROM _food_seed s
  JOIN food_item fi ON fi.name = s.name
  JOIN LATERAL unnest(string_to_array(s.allergens, ',')) AS a ON true
  JOIN allergen al ON al.name = btrim(a);

DROP TABLE _food_seed;
