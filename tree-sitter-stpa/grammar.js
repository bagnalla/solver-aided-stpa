module.exports = grammar({
    name: 'stpa',

    extras: $ => [
        /\s|\\\r?\n/,
        $.comment,
    ],

    word: $ => $.ident,

    rules: {
        system: $ => repeat(choice($.type_decl,
				   $.component,
				   $.assumption)),

	type_decl: $ => seq('type', $.ident, '{', $.ident_list, '}'),

        var_decl: $ => seq('var', $.ident, ':', $.ident),

	component: $ => seq('component', $.ident, '{', repeat(choice($.var_decl,
								     $.action,
								     $.invariant)), '}'),

	action: $ => seq('action', $.ident, '{', repeat($.constraint), '}'),

	invariant: $ => seq('invariant', '{', $._expr, '}'),
	
	assumption: $ => seq('assumption', '{', $._expr, '}'),

        constraint: $ => seq('constraint', '{', $._expr, '}'),

        _expr: $ => choice(
            $.when_expr,
            $.unary_expr,
            $.binary_expr,
            $.number,
            $._bool,
            $.dotted_name,
            $.paren_expr
        ),

        when_expr: $ => prec(0, seq(field('op', 'when'),
                                    field('left', $._expr),
                                    ',',
                                    field('right', $._expr))),

        unary_expr: $ => prec(3, prec.right(seq('not', field('e', $._expr)))),

        binary_expr: $ => {
            const op_precs = [
                ['and', 1], ['or', 1],
                ['<', 2], ['<=', 2], ['>', 2], ['>=', 2], ['=', 2], ['is', 2],
                ['+', 3], ['-', 3],
                ['*', 4], ['/', 4]
            ];

            return choice(...op_precs.map(([operator, precedence]) => {
                return prec.left(precedence, seq(
                    field('left', $._expr),
                    // @ts-ignore
                    field('op', operator),
                    field('right', $._expr),
                ));
            }));
        },

        paren_expr: $ => seq('(', $._expr, ')'),
        
        ident_list: $ => commaSep1($.ident),
        
        ident: $ => /[A-Za-z_]+/,

	dotted_name: $ => sep1($.ident, '.'),
        
        number: $ => /\d+/,

        _bool: $ => choice($.true, $.false),

        true: $ => 'true',
        
        false: $ => 'false',

        // http://stackoverflow.com/questions/13014947/regex-to-match-a-c-style-multiline-comment/36328890#36328890
        comment: _ => token(choice(
            seq('//', /(\\+(.|\r?\n)|[^\\\n])*/),
            seq(
                '/*',
                /[^*]*\*+([^/*][^*]*\*+)*/,
                '/',
            ),
        )),
    }
});

function commaSep(rule) {
    return optional(commaSep1(rule));
}

function commaSep1(rule) {
  return sep1(rule, ',');
}

function sep1(rule, separator) {
  return seq(rule, repeat(seq(separator, rule)));
}
