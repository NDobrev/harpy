(class_definition
  name: (identifier) @name) @item

(function_definition
  name: (identifier) @name) @item

(import_from_statement) @imp

(import_statement) @imp

(decorated_definition
  (decorator
    (call
      function: (attribute
        attribute: (identifier) @http)
      arguments: (argument_list
        (string) @path)))
  definition: (function_definition
    name: (identifier) @handler)) @item
