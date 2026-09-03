(function_declaration
  name: (identifier) @name) @item

(method_declaration
  name: (field_identifier) @name) @item

(type_declaration
  (type_spec
    name: (type_identifier) @name)) @item

(import_spec
  path: (interpreted_string_literal) @module) @imp

(call_expression
  function: (selector_expression
    field: (field_identifier) @http)
  arguments: (argument_list
    (interpreted_string_literal) @path)) @item
