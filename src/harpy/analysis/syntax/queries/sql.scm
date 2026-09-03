(create_table
  (object_reference) @table) @item

(drop_table
  (object_reference) @table) @item

(alter_table
  (object_reference) @table) @item

(column_definition
  name: (identifier) @column
  type: (_) @col_type) @col
