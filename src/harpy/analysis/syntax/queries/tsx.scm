(function_declaration
  name: (identifier) @name) @item

(class_declaration
  name: (type_identifier) @name) @item

(method_definition
  name: (property_identifier) @name) @item

(lexical_declaration
  (variable_declarator
    name: (identifier) @name
    value: [
      (arrow_function)
      (function_expression)
    ])) @item

(import_statement
  source: (string) @module) @imp

(decorator
  (call_expression
    function: (identifier) @http
    arguments: (arguments
      (string) @path))) @item

(call_expression
  function: (member_expression
    property: (property_identifier) @http)
  arguments: (arguments
    (string) @path)) @item
