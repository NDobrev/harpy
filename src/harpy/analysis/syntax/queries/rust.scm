(function_item
  name: (identifier) @name) @item

(struct_item
  name: (type_identifier) @name) @item

(enum_item
  name: (type_identifier) @name) @item

(use_declaration) @imp

(attribute_item
  (attribute
    (identifier) @http
    arguments: (token_tree
      (string_literal) @path))) @item
