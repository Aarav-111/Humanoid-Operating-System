Could you pls suggest some improvements for this?

━━━ TASK PLAYBOOKS ━━━

1. SWEEPING:
Pre-check: {find(type=broom)} — if no broom on board, report and stop.
           {find(dirty=true)} — identify which cells/objects need sweeping.
Zone: if user specifies area, resolve to cell list. If not, full board A1–T11.
Step 1 — Sweep row by row, one call per row:
  {sweep(A1,B1,C1,D1,E1,F1,G1,H1,I1,J1,K1,L1,M1,N1,O1,P1,Q1,R1,S1,T1)}
  Repeat for rows 2–11.
Step 2 — Second pass on any cell still showing dirty > 40%:
  {check_state(OBJECT)} on objects in those cells, re-sweep if needed.
Step 3 — Collect: {goto_coordinate = DUSTPAN_COL, DUSTPAN_ROW},
  simulate collecting by moving gripper over dustpan.
Step 4 — {check_state(broom)} — if dirty > 60%, {wash(broom)}.
NEVER mop before sweeping is fully complete.

2. MOPPING:
Pre-check: {find(type=mop)} — if missing, report and stop.
           {find(type=bucket)} — if missing, report and stop.
           Sweeping MUST be complete before mopping begins.
Step 1 — Prepare solution:
  {fill(bucket, 100)}
  {goto_coordinate = DISINFECTANT_COL, DISINFECTANT_ROW}, {pickup}
  {twist_cap(disinfectant, off)}
  {goto_coordinate = BUCKET_COL, BUCKET_ROW}, {pour_into(bucket)}
  {twist_cap(disinfectant, on)}, return disinfectant, {keep}
Step 2 — {set_state(mop, wet, true)}
Step 3 — Mop row by row:
  {mop(A1,B1,C1,...,T1)} — one call per row, all 20 columns.
  Repeat rows 2–11.
Step 4 — Monitor bucket: {check_state(bucket)} every 3 rows.
  If fillLevel < 20%: refill before continuing.
Step 5 — Return mop. Empty bucket:
  {goto_coordinate = SINK_COL, SINK_ROW}, {pour_into(sink)}, {fill(sink, 0)}.
Step 6 — {check_state(mop)} — confirm dirty level reduced.

3. WASHING UTENSILS:
Pre-check: {find(type=sink)} — must exist.
           {find(dirty=true)} — list all dirty utensils.
           Object priority order: pot/pan → plate/bowl → mug/glass → cutlery/spoon.
Step 1 — Fill sink: {fill(sink, 100)}
Step 2 — Add soap:
  {goto_coordinate = SOAP_COL, SOAP_ROW}, {pickup}
  {twist_cap(soap_bottle, off)}
  {goto_coordinate = SINK_COL, SINK_ROW}, {pour_into(sink)}
  {twist_cap(soap_bottle, on)}, return soap bottle, {keep}
Step 3 — For each dirty utensil (largest first):
  {goto_coordinate = UTENSIL_COL, UTENSIL_ROW}, {pickup}
  {goto_coordinate = SINK_COL, SINK_ROW}, {keep}
  {wash(UTENSIL_NAME)}
  {goto_coordinate = DRYING_COL, DRYING_ROW}, {pickup}, {keep}
Step 4 — Repeat Step 3 for all dirty utensils.
Step 5 — {fill(sink, 0)} — drain sink.
Step 6 — {check_state(plate)}, {check_state(mug)} etc. — confirm dirty:0.
NEVER use apply_soap/apply_cloth for utensils — use wash() which properly resets dirty state.

4. COOKING:
Pre-check: {find(type=stove)} or {find(type=oven)} — identify heat source.
           {find(type=pot)} or {find(type=pan)} — identify cookware.
           {find(type=ingredient_jar)} or {find(type=vegetable_basket)}.
PREP (always before heat):
  {goto_coordinate = KNIFE_COL, KNIFE_ROW}, {pickup}
  {goto_coordinate = CUTTING_BOARD_COL, CUTTING_BOARD_ROW}, {keep}
  {slice(vegetable_basket, 4)}
  {twist_cap(ingredient_jar, off)}, measure spices ready to add.
HEAT:
  {turn_on(stove)}, {wait_for(3)}, {check_state(stove)} — confirm temp:hot.
COOK:
  {goto_coordinate = POT_COL, POT_ROW}, {pickup}
  {goto_coordinate = STOVE_COL, STOVE_ROW}, {keep}
  {fill(pot, 60)}
  {goto_coordinate = CUTTING_BOARD_COL, CUTTING_BOARD_ROW}, {pickup}
  {goto_coordinate = STOVE_COL, STOVE_ROW}, {pour_into(pot)}
  {twist_cap(ingredient_jar, off)}
  {goto_coordinate = JAR_COL, JAR_ROW}, {pickup}
  {goto_coordinate = STOVE_COL, STOVE_ROW}, {pour_into(pot)}
  {twist_cap(ingredient_jar, on)}, return jar, {keep}
  {set_state(pot, contents, cooking)}, {wait_for(8)}
  {set_state(pot, contents, ready)}
PLATE:
  {goto_coordinate = PLATE_COL, PLATE_ROW}, {pickup}
  {goto_coordinate = STOVE_COL, STOVE_ROW}, {pour_into(plate)}
  Move plated food to serving area.
SHUTDOWN:
  {turn_off(stove)} — MANDATORY before Task_Completed.
  Return pot to storage. Return knife to rack.

5. WASHING CLOTHES:
Pre-check: {find(dirty=true)} filtered to foldable+ironable objects only.
           If nothing dirty → report "all clothes already clean", skip.
           {find(type=detergent)} — if missing, report ⚠️ NEEDS: detergent.
MACHINE WASH SEQUENCE (exact order, never deviate):
  1. {rotate_object(washing_machine, -x90)} ← door tilts upward
  2. {open(washing_machine)}
  3. For each dirty garment (shirt/pants/clothes_pile/towel):
     {goto_coordinate = GARMENT_COL, GARMENT_ROW}, {pickup}
     {goto_coordinate = MACHINE_COL, MACHINE_ROW}, {keep}
  4. {goto_coordinate = DETERGENT_COL, DETERGENT_ROW}, {pickup}
     {goto_coordinate = MACHINE_COL, MACHINE_ROW}, {pour_into(washing_machine)}
     {goto_coordinate = DETERGENT_COL, DETERGENT_ROW}, {keep}
  5. {close(washing_machine)}
  6. {rotate_object(washing_machine, +x90)} ← MUST restore upright before cycle
  7. {run_cycle(washing_machine)} ← clothes become dirty:0 wrinkled:true
  DURING WAIT → do other tasks (sweep, dust, prep food).
  8. {rotate_object(washing_machine, -x90)}, {open(washing_machine)}
  9. Retrieve clothes → laundry_basket.
  10. {close(washing_machine)}, {rotate_object(washing_machine, +x90)}
After wash → proceed to IRONING & FOLDING.

6. IRONING & FOLDING:
Pre-check: {find(wrinkled=true)} — only process wrinkled items.
           {find(dirty=true)} on same objects — if still dirty, wash first.
           {find(type=iron)} — must exist on board.
SETUP:
  Position ironing_board on a clear cell.
  {turn_on(iron)}, {wait_for(4)}
  {check_state(iron)} — MUST confirm temperature:hot before proceeding.
  If not hot: {wait_for(3)}, {check_state(iron)} again.
PER GARMENT (one at a time):
  {goto_coordinate = GARMENT_COL, GARMENT_ROW}, {pickup}
  {goto_coordinate = BOARD_COL, BOARD_ROW}, {keep}
  {iron(GARMENT_NAME)} ← sets wrinkled:false, ironed:true
  {fold(GARMENT_NAME)} ← sets folded:true
  {goto_coordinate = BOARD_COL, BOARD_ROW}, {pickup}
  {goto_coordinate = STACK_COL, STACK_ROW}, {keep}
  Repeat for all wrinkled garments.
SHUTDOWN:
  {turn_off(iron)} — MANDATORY, never skip.
  {check_state(iron)} — confirm power:false before Task_Completed.
NEVER fold before ironing. NEVER iron with cold iron. NEVER leave iron on.

7. BUYING VEGETABLES:
Pre-check: {find(type=shopping_bag)} — if missing, report ⚠️ NEEDS: shopping_bag.
           {check_state(vegetable_basket)} — if filled:true, skip and report
           "vegetable_basket already stocked".
SEQUENCE:
  Step 1 — {goto_coordinate = BAG_COL, BAG_ROW}, {pickup}
  Step 2 — Simulate market trip:
    {goto_coordinate = T, 11}, {keep}
    {open(shopping_bag)}
    {set_state(shopping_bag, contents, fresh_vegetables)}
    {set_state(shopping_bag, filled, true)}
  Step 3 — Return:
    {goto_coordinate = T, 11}, {pickup}
    {goto_coordinate = UNPACK_COL, UNPACK_ROW}, {keep}
  Step 4 — Unpack:
    {goto_coordinate = BAG_COL, BAG_ROW}, {pickup}
    {goto_coordinate = BASKET_COL, BASKET_ROW}, {pour_into(vegetable_basket)}
    {set_state(vegetable_basket, filled, true)}
  Step 5 — {close(shopping_bag)}, return bag to storage.
  Step 6 — {check_state(vegetable_basket)} — confirm filled:true.
After buying → vegetables ready for COOKING task.

8. BATHROOM CLEANING:
Pre-check: {find(type=toilet_brush)} — if missing, report ⚠️ NEEDS: toilet_brush.
           {find(type=scrub_brush)} — if missing, report ⚠️ NEEDS: scrub_brush.
           {find(type=disinfectant)} — check fillLevel > 0.
           {find(type=bucket)} — needed for mopping solution.
SEQUENCE (strict order):
  Step 1 — Prepare solution:
    {fill(bucket, 100)}
    {goto_coordinate = DISINFECTANT_COL, DISINFECTANT_ROW}, {pickup}
    {twist_cap(disinfectant, off)}
    {goto_coordinate = BUCKET_COL, BUCKET_ROW}, {pour_into(bucket)}
    {twist_cap(disinfectant, on)}, return disinfectant, {keep}
  Step 2 — Toilet scrub (2 passes minimum):
    {scrub(TOILET_COORD)}
    {scrub(TOILET_COORD)}
  Step 3 — Sink area:
    {scrub(SINK_COORD)}
  Step 4 — Tiles and floor:
    {Apply_soap(FLOOR_CELLS)}
    {scrub(FLOOR_CELLS)}
    {mop(FLOOR_CELLS)}
  Step 5 — Clean tools:
    {wash(toilet_brush)}, {wash(scrub_brush)}
    {check_state(toilet_brush)}, {check_state(scrub_brush)} — confirm dirty:0
  Step 6 — Dispose dirty water:
    {goto_coordinate = SINK_COL, SINK_ROW}, {pour_into(sink)}, {fill(sink, 0)}
NEVER skip tool cleaning — dirty tools spread contamination.

9. DUSTING:
Pre-check: {find(type=duster)} — if missing, report ⚠️ NEEDS: duster.
           {find(dirty=true)} — identify objects/surfaces needing dusting.
SEQUENCE (always high-to-low — dust falls downward):
  Step 1 — Large/heavy objects first (oven, stove, sink, washing_machine):
    {Apply_cloth(OBJ_COORD)}
    If dirty > 60%: second pass immediately.
  Step 2 — Medium objects (boxes, baskets, laundry_basket):
    {Apply_cloth(OBJ_COORD)}
  Step 3 — Small objects (plates, mugs, bottles, jars):
    {Apply_cloth(OBJ_COORD)}
  Step 4 — Open surfaces and empty cells:
    {Apply_cloth(A1,B1,...)} for each surface row.
  Step 5 — {check_state(duster)} — if dirty > 50%:
    {wash(duster)}, {check_state(duster)} confirm clean.
  Step 6 — Follow with sweep pass to catch fallen dust:
    {sweep(ALL_CELLS)}
FULL CLEAN ORDER: dust → sweep → mop. Never break this sequence.

10. TIDYING:
Pre-check: Read full board state — note every object's current position.
           {find(type=all)} to get complete inventory.
ZONE MAP (always organize into these zones):
  A1–D4:  Cleaning tools (broom, mop, bucket, brushes, disinfectant)
  E1–H4:  Dining (plates, bowls, mugs, glasses, cutlery, napkins)
  I1–L4:  Kitchen (stove, pot, pan, ingredient jars, cutting_board, knife)
  M1–P4:  Laundry (washing_machine, basket, clothes, iron, ironing_board)
  Q1–T4:  Pantry (bottles, boxes, vegetable_basket, shopping_bag)
  A5–T11: Clear working area — nothing stored here permanently.
SEQUENCE:
  Step 1 — Heavy appliances first (drag, never pickup):
    {drag_from_coordinate(FROM)_to_coordinate(TO)} for stove, sink,
    washing_machine, oven to correct zones.
  Step 2 — Medium objects (laundry_basket, ironing_board, bucket):
    {pickup} → {goto_coordinate = TARGET} → {keep}
  Step 3 — Light objects in bulk, nearest-first:
    Same-category items placed adjacent to each other.
  Step 4 — Wipe all surfaces:
    {Apply_cloth(ALL_SURFACE_CELLS)}
  Step 5 — Final verification:
    {check_state()} on 3–4 key objects to confirm positions.
    Confirm working area A5–T11 is clear.
GROUPING RULE: same category items must TOUCH each other.
  All bottles adjacent. All mugs adjacent. Never mix categories.
