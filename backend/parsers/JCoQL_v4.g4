grammar JCoQL;

// JCoQL 4.0 Grammar - ANTLR4 Python Target
// Converted from JCoQL.txt (ANTLR3/Java) to ANTLR4/Python
// Syntax rules only - no semantic actions

// ########### Parser Rules ###########

start
    : ( useDbRule
      | getCollectionRule
      | getDictionaryRule
      | lookupFromWebRule
      | saveAsRule
      | mergeCollectionsRule
      | intersectCollectionsRule
      | subtractCollectionsRule
      | filterRule
      | joinOfCollectionsRule
      | trajectoryMatchingRule
      | groupRule
      | expandRule
      | createJavaScriptFunctionRule
      | createJavaFunctionRule
      | createEvaluatorRule
      | createFuzzyOperatorRule
      | createFuzzyAggregatorRule
      | createFuzzyEvaluatorRule
      | createFuzzySetModelRule
      | createGenericFuzzySetOperatorRule
      | createGenericFuzzyEvaluatorRule
      )* EOF
    ;

// Collection Reference
collectionReferenceRule
    : ID ( AT ID )? ( AS ID )?
    ;

// Field Reference
fieldRefRule
    : FIELD_NAME+
    ;

// Build Action
buildActionRule
    : BUILD objectStructureRule
    | ADD_ST FIELDS objectStructureRule
    | REMOVE FIELDS LBR fieldRefRule ( COMMA fieldRefRule )* RBR
    ;

// Object Structure
objectStructureRule
    : LBR outputFieldSpecRule ( COMMA outputFieldSpecRule )* RBR
    ;

// Output Field Spec
outputFieldSpecRule
    : fieldRefRule ( COLON ( objectStructureRule | factorRule ) )?
    | UNNEST fieldRefRule
    ;

// Geometric Option
geometricOptionRule
    : KEEPING GEOMETRY
    | SETTING GEOMETRY
      ( POINT LP fieldRefRule COMMA fieldRefRule RP
      | AGGREGATE LP fieldRefRule RP
      | fieldRefRule
      | TO_POLYLINE LP fieldRefRule RP
      )
    ;

// Drop Geometry
dropGeometryRule
    : DROPPING GEOMETRY
    ;

// Case Clause
caseClauseRule
    : ( CASES | CASE ) ( whereCaseRule )+ ( othersRule )?
    ;

// Others
othersRule
    : ( KEEP | DROP ) OTHERS
    ;

// Where Case
whereCaseRule
    : WHERE orConditionRule ( generateSectionRule )?
    ;

// Generate Section
generateSectionRule
    : GENERATE
      ( geometricOptionRule )?
      ( checkForFuzzySetRule )?
      ( alphaCutRule )?
      ( buildActionRule )*
      ( keepDropFuzzySetsRule )?
      ( dropGeometryRule )?
    ;

// Conditions
orConditionRule
    : andConditionRule ( OR andConditionRule )*
    ;

andConditionRule
    : notConditionRule ( AND notConditionRule )*
    ;

notConditionRule
    : NOT? predicateRule
    ;

// Predicate
predicateRule
    : expressionRule ( compareRule | inRangeRule )?
    | nullPredicateRule
    | withPredicateRule
    | withoutPredicateRule
    | wukFuzzyPredicateRule
    ;

// Compare
compareRule
    : comparatorRule expressionRule
    ;

// In Range
inRangeRule
    : INRANGE ( LB | LP ) numericRule COMMA numericRule ( RP | RB )
    ;

// Null Predicate
nullPredicateRule
    : FIELD fieldRefRule ( ISNULL | ISNOTNULL )
    ;

// Fuzzy Predicate
wukFuzzyPredicateRule
    : ( WITHIN | KNOWN | UNKNOWN ) FUZZY SETS ID ( COMMA ID )*
    ;

// Without Predicate
withoutPredicateRule
    : WITHOUT fieldRefRule ( COMMA fieldRefRule )*
    ;

// With Predicate
withPredicateRule
    : WITH ( ( ID | ARRAY | GEOMETRY ) )? fieldRefRule ( COMMA fieldRefRule )*
    ;

// Expression
expressionRule
    : ( termRule | ( ADD | SUB ) termRule ) ( ( ADD | SUB ) termRule )*
    ;

// Term
termRule
    : factorRule ( ( MUL | DIV ) factorRule )*
    ;

// Factor
factorRule
    : LP orConditionRule RP
    | fieldRefRule
    | valueRule
    | ID ( LP functionParamsRule? RP )?
    | specialFunctionRule
    | LB factorRule ( COMMA factorRule )* RB
    ;

// Special Functions
specialFunctionRule
    : MEMBERSHIP_TO LP ID RP
    | EXTENT LP ID RP
    | DEGREE LP ID FIELD_NAME? RP
    | HASH_NAME FIELD_NAME?
    | MEMBERSHIP_ARRAY LP ( ALL | ID FROM_ARRAY fieldRefRule | LB ID ( COMMA ID )* RB ) RP
    | EXTRACT_ARRAY LP fieldRefRule FROM_ARRAY fieldRefRule RP
    | IF LP LP orConditionRule RP COMMA restrictedExpressionRule COMMA restrictedExpressionRule RP
    | IF_ERROR LP restrictedExpressionRule COMMA valueRule RP
    | TRANSLATE LP restrictedExpressionRule COMMA ID ( COMMA BOOLEAN ( COMMA ( APEX_VALUE | QUOTED_VALUE ) )? )? RP
    | arrayFunctionRule
    ;

// Value
valueRule
    : INT
    | FLOAT
    | BOOLEAN
    | APEX_VALUE
    | QUOTED_VALUE
    ;

// Array Function
arrayFunctionRule
    : ARRAY_FUNCTION LP ( fieldRefRule | LB restrictedExpressionRule ( COMMA restrictedExpressionRule )* RB ) COMMA ID ( COMMA ( fieldRefRule ( COMMA fieldRefRule )* | DOCUMENTS COMMA fieldRefRule ( COMMA fieldRefRule )* ) )? RP
    ;

// Restricted Expression
restrictedExpressionRule
    : ( restrictedTermRule | ( ADD | SUB ) restrictedTermRule ) ( ( ADD | SUB ) restrictedTermRule )*
    ;

restrictedTermRule
    : restrictedFactorRule ( ( MUL | DIV ) restrictedFactorRule )*
    ;

restrictedFactorRule
    : LP restrictedExpressionRule RP
    | fieldRefRule
    | valueRule
    | ID ( LP functionParamsRule? RP )?
    | specialFunctionRule
    | LB restrictedFactorRule ( COMMA restrictedFactorRule )* RB
    ;

// Function Parameters
functionParamsRule
    : restrictedExpressionRule ( COMMA restrictedExpressionRule )*
    ;

// Comparator
comparatorRule
    : EQ | NEQ | LT | GT | LE | GE
    ;

// Numeric
numericRule
    : ( ADD | SUB )? ( FLOAT | INT )
    ;

// Fuzzy Extensions
checkForFuzzySetRule
    : CHECK_FOR ID? FUZZY SET ID USING usingOrConditionRule ( COMMA ID? FUZZY SET ID USING usingOrConditionRule )*
    ;

usingOrConditionRule
    : usingAndConditionRule ( OR usingAndConditionRule )*
    ;

usingAndConditionRule
    : usingNotConditionRule ( AND usingNotConditionRule )*
    ;

usingNotConditionRule
    : NOT? usingPredicateRule
    ;

usingPredicateRule
    : LP usingOrConditionRule RP
    | ID ( LP functionParamsRule? RP )?
    | IF_FAILS LP usingOrConditionRule COMMA numericRule RP
    ;

alphaCutRule
    : ALPHACUT numericRule ON ID FIELD_NAME? ( COMMA numericRule ON ID FIELD_NAME? )*
    ;

keepDropFuzzySetsRule
    : DEFUZZIFY
    | DROPPING ALL FUZZY SETS
    | KEEPING ALL FUZZY SETS
    | DROPPING FUZZY SETS ID ( COMMA ID )*
    | KEEPING FUZZY SETS ID ( COMMA ID )*
    ;

// Main Instructions

getCollectionRule
    : GET COLLECTION ID ( AT ID )? SC
    ;

getDictionaryRule
    : GET DICTIONARY ID ( AT ID )? SC
    ;

lookupFromWebRule
    : LOOKUP FROM_WEB APEX_VALUE AS ID SC
    ;

saveAsRule
    : SAVE AS ID ( AT ID )? SC
    ;

mergeCollectionsRule
    : ( ALL )? MERGE COLLECTIONS collectionReferenceRule ( COMMA collectionReferenceRule )+ ( REMOVE DUPLICATES )? SC
    ;

intersectCollectionsRule
    : INTERSECT COLLECTIONS collectionReferenceRule COMMA collectionReferenceRule SC
    ;

subtractCollectionsRule
    : SUBTRACT COLLECTIONS collectionReferenceRule COMMA collectionReferenceRule SC
    ;

filterRule
    : FILTER caseClauseRule SC
    ;

joinOfCollectionsRule
    : JOIN OF COLLECTIONS collectionReferenceRule COMMA collectionReferenceRule ( caseClauseRule )? SC
    ;

groupRule
    : GROUP ( groupPartitionRule )+ ( othersRule )? SC
    ;

groupPartitionRule
    : PARTITION orConditionRule BY fieldRefRule ( COMMA fieldRefRule )* INTO fieldRefRule ( DROP GROUPING FIELDS )? ( ORDER BY sortingFieldRule ( COMMA sortingFieldRule )* ( KEEP UNCOMPARABLE )? )? ( generateSectionRule )?
    ;

sortingFieldRule
    : fieldRefRule TYPE ID ( VERSUS )?
    ;

expandRule
    : EXPAND ( unpackRule )+ ( othersRule )? SC
    ;

unpackRule
    : UNPACK orConditionRule ARRAY fieldRefRule TO ID ( generateSectionRule )?
    ;

trajectoryMatchingRule
    : TRAJECTORY MATCHING collectionReferenceRule COMMA collectionReferenceRule ( trajectoryPartitionRule )+ ( othersRule )? SC
    ;

trajectoryPartitionRule
    : PARTITION orConditionRule ( partitionMatchingRule )+
    ;

partitionMatchingRule
    : MATCHING fieldRefRule WRT fieldRefRule THRESHOLD LP ID RP numericRule ( WHERE orConditionRule )? INTO fieldRefRule ( ADDING fieldRefRule TO INPUT )? ( MIN_SIMILARITY numericRule )?
    ;

useDbRule
    : USE DB ( ID | APEX_VALUE ) ( AS ( ID | APEX_VALUE ) )? ( COMMA DB ( ID | APEX_VALUE ) ( AS ( ID | APEX_VALUE ) )? )* ON ( DEFAULT SERVER | SERVER ( ID | APEX_VALUE ) ( ( ID | APEX_VALUE ) )? ) SC
    ;

// Placeholder rules for complex features
createJavaScriptFunctionRule : CREATE JAVASCRIPT FUNCTION ID SC ;
createJavaFunctionRule : CREATE JAVA FUNCTION ID SC ;
createEvaluatorRule : CREATE ID EVALUATOR ID SC ;
createFuzzyOperatorRule : CREATE FUZZY OPERATOR ID SC ;
createFuzzyAggregatorRule : CREATE FUZZY AGGREGATOR ID SC ;
createFuzzyEvaluatorRule : CREATE ID FUZZY EVALUATOR ID SC ;
createFuzzySetModelRule : CREATE FUZZY SET MODEL ID SC ;
createGenericFuzzySetOperatorRule : CREATE ID FUZZY OPERATOR ID SC ;
createGenericFuzzyEvaluatorRule : CREATE ID FUZZY EVALUATOR ID SC ;

// ########### Lexer Rules ###########

// Boolean Operators
AND : 'AND' ;
OR : 'OR' ;
NOT : 'NOT' ;

// Keywords
ADDING : 'ADDING' ;
ADD_ST : 'ADD' ;
AGGREGATE : 'AGGREGATE' ;
AGGREGATOR : 'AGGREGATOR' ;
ALL : 'ALL' ;
ALPHACUT : 'ALPHACUT' ;
ARRAY : 'ARRAY' ;
ARRAY_FUNCTION : ( 'MIN' | 'MAX' | 'AVG' | 'SUM' ) '_ARRAY' ;
AS : 'AS' ;
BODY : 'BODY' ;
END_BODY : 'END' WS 'BODY' ;
BOOLEAN : 'TRUE' | 'FALSE' ;
BUILD : 'BUILD' ;
BY : 'BY' ;
CALL : 'CALL' ;
CASE : 'CASE' ;
CASES : 'CASES' ;
CHECK_FOR : 'CHECK' WS 'FOR' ;
CLASS : 'CLASS' ;
COLLECTION : 'COLLECTION' ;
COLLECTIONS : 'COLLECTIONS' ;
CONSTRAINT : 'CONSTRAINT' ;
CREATE : 'CREATE' ;
CUMULATE : 'CUMULATE' ;
DB : 'DB' ;
DEFAULT : 'DEFAULT' ;
DEFUZZIFY : 'DEFUZZIFY' ;
DEGREE : 'DEGREE' ;
DEGREES : 'DEGREES' ;
DERIVE : 'DERIVE' ;
DERIVED : 'DERIVED' ;
DICTIONARY : 'DICTIONARY' ;
DIRECTION : 'DIRECTION' ;
DISTANCE : 'DISTANCE' ;
DOCUMENTS : 'DOCUMENTS' ;
DROP : 'DROP' ;
DROPPING : 'DROPPING' ;
DUPLICATES : 'DUPLICATES' ;
EACH : 'EACH' ;
EXPAND : 'EXPAND' ;
EXTENT : 'EXTENT' ;
EXTRACT_ARRAY : 'EXTRACT_ARRAY' ;
EVALUATE : 'EVALUATE' ;
EVALUATOR : 'EVALUATOR' ;
FIELD : 'FIELD' ;
FIELDS : 'FIELDS' ;
FILE : 'FILE' ;
FILTER : 'FILTER' ;
FIRST : 'FIRST' ;
FOR : 'FOR' ;
FROM_WEB : 'FROM' WS 'WEB' ;
FROM_ARRAY : 'FROM' WS 'ARRAY' ;
FUZZY : 'FUZZY' ;
FUNCTION : 'FUNCTION' ;
GENERATE : 'GENERATE' ;
GEOMETRY : 'GEOMETRY' ;
GET : 'GET' ;
GROUP : 'GROUP' ;
GROUPING : 'GROUPING' ;
HOWINCLUDE : 'HOW_INCLUDE' ;
HOWINTERSECT : 'HOW_INTERSECT' ;
HOWMEET : 'HOW_MEET' ;
IF : 'IF' ;
IF_ERROR : 'IF_ERROR' ;
IF_FAILS : 'IF_FAILS' ;
IMPORT : 'IMPORT' ;
INCLUDED : 'INCLUDED' ;
INPUT : 'INPUT' ;
INRANGE : 'IN_RANGE' ;
INTERSECT : 'INTERSECT' ;
INTERSECTION : 'INTERSECTION' ;
IN : 'IN' ;
INTO : 'INTO' ;
ISNULL : 'IS' WS 'NULL' ;
ISNOTNULL : 'IS' WS 'NOT' WS 'NULL' ;
JOIN : 'JOIN' ;
JAVA : 'JAVA' ;
JAVASCRIPT : 'JAVASCRIPT' ;
KEEP : 'KEEP' ;
KEEPING : 'KEEPING' ;
KNOWN : 'KNOWN' ;
LAST : 'LAST' ;
LEFT : 'LEFT' ;
LOCALLY : 'LOCALLY' ;
LOOKUP : 'LOOKUP' ;
MATCHING : 'MATCHING' ;
MAXIMUM : 'MAXIMUM' ;
MEET : 'MEET' ;
MEMBERSHIP_ARRAY : 'MEMBERSHIP_ARRAY' ;
MEMBERSHIP_TO : 'MEMBERSHIP_TO' | 'MEMBERSHIP_OF' ;
MERGE : 'MERGE' ;
MIN_SIMILARITY : 'MIN_SIMILARITY' ;
MINIMUM : 'MINIMUM' ;
MODEL : 'MODEL' ;
OF : 'OF' ;
ON : 'ON' ;
OPERATOR : 'OPERATOR' ;
ORIENTATION : 'ORIENTATION' ;
OTHERS : 'OTHERS' ;
ORDER : 'ORDER' | 'SORTED' ;
PARAMETERS : 'PARAMETERS' ;
PARTITION : 'PARTITION' ;
POINT : 'POINT' ;
POLYLINE : 'POLYLINE' ;
POS : 'POS' ;
PRECONDITION : 'PRECONDITION' ;
PRODUCT : 'PRODUCT' ;
RESOLVING : 'RESOLVING' ;
RIGHT : 'RIGHT' ;
REMOVE : 'REMOVE' ;
SAVE : 'SAVE' ;
SERVER : 'SERVER' ;
SET : 'SET' ;
SETS : 'SETS' ;
SETTING : 'SETTING' ;
SORT : 'SORT' ;
SUBTRACT : 'SUBTRACT' ;
SUM : 'SUM' ;
TO : 'TO' ;
TO_POLYLINE : 'TO_POLYLINE' ;
THRESHOLD : 'THRESHOLD' ;
TRANSLATE : 'TRANSLATE' ;
TRAJECTORY : 'TRAJECTORY' ;
TYPE : 'TYPE' ;
UNCOMPARABLE : 'UNCOMPARABLE' ;
UNKNOWN : 'UNKNOWN' ;
UNNEST : 'UNNEST' ;
UNPACK : 'UNPACK' ;
USE : 'USE' ;
USING : 'USING' ;
VERSUS : 'DESC' | 'ASC' ;
WEB : 'WEB' ;
WHERE : 'WHERE' ;
WITH : 'WITH' ;
WITHIN : 'WITHIN' ;
WITHOUT : 'WITHOUT' ;
WRT : 'WRT' ;

// Literals
INT : '0' | [1-9] [0-9]* ;
FLOAT : [1-9] [0-9]* DOT [0-9]+ | '0' DOT [0-9]+ ;
ID : [A-Za-z] [A-Za-z0-9_]* ;
FIELD_NAME : DOT [A-Za-z0-9~_]+ | DOT '"' ~["]* '"' ;
HASH_NAME : '#' [A-Za-z0-9~_]+ | '#' '"' ~["]* '"' ;

// Punctuation
AT : '@' ;
EQ : '=' ;
NEQ : '!=' ;
LE : '<=' ;
GE : '>=' ;
LT : '<' ;
GT : '>' ;
DOT : '.' ;
ADD : '+' ;
SUB : '-' ;
MUL : '*' ;
DIV : '/' ;
EXP : '^' ;
COMMA : ',' ;
COLON : ':' ;
SC : ';' ;
LP : '(' ;
RP : ')' ;
LB : '[' ;
RB : ']' ;
LBR : '{' ;
RBR : '}' ;
APEX : '\'' ;
QUOTE : '"' ;
TILDE : '~' ;

// String Literals
APEX_VALUE : '\'' ~[']* '\'' ;
QUOTED_VALUE : '"' ~["]* '"' ;

// Whitespace
fragment WS : [ \t\r\n]+ ;
WHITE_SPACES : WS -> skip ;

// Comments
COMMENT : '//' ~[\r\n]* '\r'? '\n' -> skip
        | '/*' .*? '*/' -> skip
        ;

// Catch-all
SCAN_ERROR : . ;
