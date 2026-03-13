grammar JCoQL;

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

// CORREZIONE DEFINITIVA ID: Include booleani e keywords per evitare blocchi nelle espressioni
anyId 
    : ID | ORDER | CASE | CASES | FILTER | GET | COLLECTION | FIELDS 
    | GROUP | JOIN | BOOLEAN | WHERE | GENERATE | OTHERS | KEEP | DROP 
    ;

collectionReferenceRule : anyId ( AT anyId )? ( AS anyId )? ;
fieldRefRule : FIELD_NAME+ ;

buildActionRule
    : BUILD objectStructureRule
    | ADD_ST FIELDS objectStructureRule
    | REMOVE FIELDS LBR fieldRefRule ( COMMA fieldRefRule )* RBR
    ;

objectStructureRule : LBR outputFieldSpecRule ( COMMA outputFieldSpecRule )* RBR ;

outputFieldSpecRule
    : fieldRefRule ( COLON ( objectStructureRule | factorRule ) )?
    | UNNEST fieldRefRule
    ;

geometricOptionRule
    : KEEPING GEOMETRY
    | SETTING GEOMETRY
      ( POINT LP fieldRefRule COMMA fieldRefRule RP
      | AGGREGATE LP fieldRefRule RP
      | fieldRefRule
      | TO_POLYLINE LP fieldRefRule RP
      )
    ;

dropGeometryRule : DROPPING GEOMETRY ;

caseClauseRule : ( CASES | CASE ) ( whereCaseRule )+ ( othersRule )? ;
othersRule : ( KEEP | DROP ) OTHERS ;
whereCaseRule : WHERE orConditionRule ( generateSectionRule )? ;

generateSectionRule
    : GENERATE
      ( geometricOptionRule )?
      ( checkForFuzzySetRule )?
      ( alphaCutRule )?
      ( buildActionRule )*
      ( keepDropFuzzySetsRule )?
      ( dropGeometryRule )?
    ;

orConditionRule : andConditionRule ( OR andConditionRule )* ;
andConditionRule : notConditionRule ( AND notConditionRule )* ;
notConditionRule : NOT? predicateRule ;

predicateRule
    : expressionRule ( compareRule | inRangeRule )?
    | nullPredicateRule
    | withPredicateRule
    | withoutPredicateRule
    | wukFuzzyPredicateRule
    ;

compareRule : comparatorRule expressionRule ;
inRangeRule : INRANGE ( LB | LP ) numericRule COMMA numericRule ( RP | RB ) ;

nullPredicateRule : FIELD? fieldRefRule ( ISNULL | ISNOTNULL ) ;

wukFuzzyPredicateRule : ( WITHIN | KNOWN | UNKNOWN ) FUZZY SETS anyId ( COMMA anyId )* ;
withoutPredicateRule : WITHOUT fieldRefRule ( COMMA fieldRefRule )* ;
withPredicateRule : WITH ( ( anyId | ARRAY | GEOMETRY ) )? fieldRefRule ( COMMA fieldRefRule )* ;

expressionRule : ( termRule | ( ADD | SUB ) termRule ) ( ( ADD | SUB ) termRule )* ;
termRule : factorRule ( ( MUL | DIV ) factorRule )* ;

factorRule
    : LP orConditionRule RP
    | fieldRefRule
    | valueRule
    | anyId ( LP functionParamsRule? RP )?
    | specialFunctionRule
    | LB factorRule ( COMMA factorRule )* RB
    ;

specialFunctionRule
    : MEMBERSHIP_TO LP anyId RP
    | EXTENT LP anyId RP
    | DEGREE LP anyId FIELD_NAME? RP
    | HASH_NAME FIELD_NAME?
    | MEMBERSHIP_ARRAY LP ( ALL | anyId FROM_ARRAY fieldRefRule | LB anyId ( COMMA anyId )* RB ) RP
    | EXTRACT_ARRAY LP fieldRefRule FROM_ARRAY fieldRefRule RP
    | IF LP LP orConditionRule RP COMMA restrictedExpressionRule COMMA restrictedExpressionRule RP
    | IF_ERROR LP restrictedExpressionRule COMMA valueRule RP
    | TRANSLATE LP restrictedExpressionRule COMMA anyId ( COMMA BOOLEAN ( COMMA ( APEX_VALUE | QUOTED_VALUE ) )? )? RP
    | arrayFunctionRule
    ;

valueRule : INT | FLOAT | BOOLEAN | APEX_VALUE | QUOTED_VALUE ;

arrayFunctionRule
    : ARRAY_FUNCTION LP ( fieldRefRule | LB restrictedExpressionRule ( COMMA restrictedExpressionRule )* RB ) COMMA anyId ( COMMA ( fieldRefRule ( COMMA fieldRefRule )* | DOCUMENTS COMMA fieldRefRule ( COMMA fieldRefRule )* ) )? RP
    ;

restrictedExpressionRule : ( restrictedTermRule | ( ADD | SUB ) restrictedTermRule ) ( ( ADD | SUB ) restrictedTermRule )* ;
restrictedTermRule : restrictedFactorRule ( ( MUL | DIV ) restrictedFactorRule )* ;

restrictedFactorRule
    : LP restrictedExpressionRule RP
    | fieldRefRule
    | valueRule
    | anyId ( LP functionParamsRule? RP )?
    | specialFunctionRule
    | LB restrictedFactorRule ( COMMA restrictedFactorRule )* RB
    ;

functionParamsRule : restrictedExpressionRule ( COMMA restrictedExpressionRule )* ;
comparatorRule : EQ | NEQ | LT | GT | LE | GE ;
numericRule : ( ADD | SUB )? ( FLOAT | INT ) ;

checkForFuzzySetRule : CHECK_FOR anyId? FUZZY SET anyId USING usingOrConditionRule ( COMMA anyId? FUZZY SET anyId USING usingOrConditionRule )* ;
usingOrConditionRule : usingAndConditionRule ( OR usingAndConditionRule )* ;
usingAndConditionRule : usingNotConditionRule ( AND usingNotConditionRule )* ;
usingNotConditionRule : NOT? usingPredicateRule ;

usingPredicateRule
    : LP usingOrConditionRule RP
    | anyId ( LP functionParamsRule? RP )?
    | IF_FAILS LP usingOrConditionRule COMMA numericRule RP
    ;

alphaCutRule : ALPHACUT numericRule ON anyId FIELD_NAME? ( COMMA numericRule ON anyId FIELD_NAME? )* ;

keepDropFuzzySetsRule
    : DEFUZZIFY
    | DROPPING ALL FUZZY SETS
    | KEEPING ALL FUZZY SETS
    | DROPPING FUZZY SETS anyId ( COMMA anyId )*
    | KEEPING FUZZY SETS anyId ( COMMA anyId )*
    ;

getCollectionRule : GET COLLECTION anyId ( AT anyId )? SC ;
getDictionaryRule : GET DICTIONARY anyId ( AT anyId )? SC ;
lookupFromWebRule : LOOKUP FROM_WEB APEX_VALUE AS anyId SC ;
saveAsRule : SAVE AS anyId ( AT anyId )? SC ;
mergeCollectionsRule : ( ALL )? MERGE COLLECTIONS collectionReferenceRule ( COMMA collectionReferenceRule )+ ( REMOVE DUPLICATES )? SC ;
intersectCollectionsRule : INTERSECT COLLECTIONS collectionReferenceRule COMMA collectionReferenceRule SC ;
subtractCollectionsRule : SUBTRACT COLLECTIONS collectionReferenceRule COMMA collectionReferenceRule SC ;
filterRule : FILTER caseClauseRule SC ;
joinOfCollectionsRule : JOIN OF COLLECTIONS collectionReferenceRule COMMA collectionReferenceRule ( caseClauseRule )? SC ;
groupRule : GROUP ( groupPartitionRule )+ ( othersRule )? SC ;
groupPartitionRule : PARTITION orConditionRule BY fieldRefRule ( COMMA fieldRefRule )* INTO fieldRefRule ( DROP GROUPING FIELDS )? ( ORDER BY sortingFieldRule ( COMMA sortingFieldRule )* ( KEEP UNCOMPARABLE )? )? ( generateSectionRule )? ;
sortingFieldRule : fieldRefRule TYPE anyId ( VERSUS )? ;
expandRule : EXPAND ( unpackRule )+ ( othersRule )? SC ;
unpackRule : UNPACK orConditionRule ARRAY fieldRefRule TO anyId ( generateSectionRule )? ;
trajectoryMatchingRule : TRAJECTORY MATCHING collectionReferenceRule COMMA collectionReferenceRule ( trajectoryPartitionRule )+ ( othersRule )? SC ;
trajectoryPartitionRule : PARTITION orConditionRule ( partitionMatchingRule )+ ;
partitionMatchingRule : MATCHING fieldRefRule WRT fieldRefRule THRESHOLD LP anyId RP numericRule ( WHERE orConditionRule )? INTO fieldRefRule ( ADDING fieldRefRule TO INPUT )? ( MIN_SIMILARITY numericRule )? ;
useDbRule : USE DB ( anyId | APEX_VALUE ) ( AS ( anyId | APEX_VALUE ) )? ( COMMA DB ( anyId | APEX_VALUE ) ( AS ( anyId | APEX_VALUE ) )? )* ON ( DEFAULT SERVER | SERVER ( anyId | APEX_VALUE ) ( ( anyId | APEX_VALUE ) )? ) SC ;

createJavaScriptFunctionRule : CREATE JAVASCRIPT FUNCTION anyId SC ;
createJavaFunctionRule : CREATE JAVA FUNCTION anyId SC ;
createEvaluatorRule : CREATE anyId EVALUATOR anyId SC ;
createFuzzyOperatorRule : CREATE FUZZY OPERATOR anyId SC ;
createFuzzyAggregatorRule : CREATE FUZZY AGGREGATOR anyId SC ;
createFuzzyEvaluatorRule : CREATE anyId FUZZY EVALUATOR anyId SC ;
createFuzzySetModelRule : CREATE FUZZY SET MODEL anyId SC ;
createGenericFuzzySetOperatorRule : CREATE anyId FUZZY OPERATOR anyId SC ;
createGenericFuzzyEvaluatorRule : CREATE anyId FUZZY EVALUATOR anyId SC ;

// ########### Lexer Rules ###########

AND : 'AND' | 'and' ;
OR : 'OR' | 'or' ;
NOT : 'NOT' | 'not' ;
ADDING : 'ADDING' | 'adding' ;
ADD_ST : 'ADD' | 'add' ;
AGGREGATE : 'AGGREGATE' | 'aggregate' ;
AGGREGATOR : 'AGGREGATOR' | 'aggregator' ;
ALL : 'ALL' | 'all' ;
ALPHACUT : 'ALPHACUT' | 'alphacut' ;
ARRAY : 'ARRAY' | 'array' ;
ARRAY_FUNCTION : ('MIN' | 'MAX' | 'AVG' | 'SUM' | 'min' | 'max' | 'avg' | 'sum') '_ARRAY' ;
AS : 'AS' | 'as' ;
BOOLEAN : 'TRUE' | 'FALSE' | 'true' | 'false' | 'True' | 'False' ;
BUILD : 'BUILD' | 'build' ;
BY : 'BY' | 'by' ;
CASE : 'CASE' | 'case' ;
CASES : 'CASES' | 'cases' ;
CHECK_FOR : ('CHECK' | 'check') [ \t\r\n\u00A0]+ ('FOR' | 'for') ;
COLLECTION : 'COLLECTION' | 'collection' ;
COLLECTIONS : 'COLLECTIONS' | 'collections' ;
CREATE : 'CREATE' | 'create' ;
DB : 'DB' | 'db' ;
DEFAULT : 'DEFAULT' | 'default' ;
DEFUZZIFY : 'DEFUZZIFY' | 'defuzzify' ;
DEGREE : 'DEGREE' | 'degree' ;
DICTIONARY : 'DICTIONARY' | 'dictionary' ;
DOCUMENTS : 'DOCUMENTS' | 'documents' ;
DROP : 'DROP' | 'drop' ;
DROPPING : 'DROPPING' | 'dropping' ;
DUPLICATES : 'DUPLICATES' | 'duplicates' ;
EXPAND : 'EXPAND' | 'expand' ;
EXTENT : 'EXTENT' | 'extent' ;
EXTRACT_ARRAY : ('EXTRACT' | 'extract') '_ARRAY' ;
EVALUATOR : 'EVALUATOR' | 'evaluator' ;
FIELD : 'FIELD' | 'field' ;
FIELDS : 'FIELDS' | 'fields' ;
FILTER : 'FILTER' | 'filter' ;
FROM_WEB : ('FROM' | 'from') [ \t\r\n\u00A0]+ ('WEB' | 'web') ;
FROM_ARRAY : ('FROM' | 'from') [ \t\r\n\u00A0]+ ('ARRAY' | 'array') ;
FUZZY : 'FUZZY' | 'fuzzy' ;
FUNCTION : 'FUNCTION' | 'function' ;
GENERATE : 'GENERATE' | 'generate' ;
GEOMETRY : 'GEOMETRY' | 'geometry' ;
GET : 'GET' | 'get' ;
GROUP : 'GROUP' | 'group' ;
GROUPING : 'GROUPING' | 'grouping' ;
IF : 'IF' | 'if' ;
IF_ERROR : 'IF_ERROR' | 'if_error' ;
IF_FAILS : 'IF_FAILS' | 'if_fails' ;
INPUT : 'INPUT' | 'input' ;
INRANGE : 'IN_RANGE' | 'in_range' ;
INTERSECT : 'INTERSECT' | 'intersect' ;
INTO : 'INTO' | 'into' ;
ISNULL : ('IS' | 'is') [ \t\r\n\u00A0]+ ('NULL' | 'null') ;
ISNOTNULL : ('IS' | 'is') [ \t\r\n\u00A0]+ ('NOT' | 'not') [ \t\r\n\u00A0]+ ('NULL' | 'null') ;
JOIN : 'JOIN' | 'join' ;
JAVA : 'JAVA' | 'java' ;
JAVASCRIPT : 'JAVASCRIPT' | 'javascript' ;
KEEP : 'KEEP' | 'keep' ;
KEEPING : 'KEEPING' | 'keeping' ;
KNOWN : 'KNOWN' | 'known' ;
LOOKUP : 'LOOKUP' | 'lookup' ;
MATCHING : 'MATCHING' | 'matching' ;
MEMBERSHIP_ARRAY : 'MEMBERSHIP_ARRAY' ;
MEMBERSHIP_TO : ('MEMBERSHIP' | 'membership') '_' ('TO' | 'to' | 'OF' | 'of') ;
MERGE : 'MERGE' | 'merge' ;
MIN_SIMILARITY : 'MIN_SIMILARITY' ;
MODEL : 'MODEL' | 'model' ;
OF : 'OF' | 'of' ;
ON : 'ON' | 'on' ;
OPERATOR : 'OPERATOR' | 'operator' ;
OTHERS : 'OTHERS' | 'others' ;
ORDER : 'ORDER' | 'order' | 'SORTED' | 'sorted' ;
PARTITION : 'PARTITION' | 'partition' ;
POINT : 'POINT' | 'point' ;
REMOVE : 'REMOVE' | 'remove' ;
SAVE : 'SAVE' | 'save' ;
SERVER : 'SERVER' | 'server' ;
SET : 'SET' | 'set' ;
SETS : 'SETS' | 'sets' ;
SETTING : 'SETTING' | 'setting' ;
SUBTRACT : 'SUBTRACT' | 'subtract' ;
TO : 'TO' | 'to' ;
TO_POLYLINE : 'TO_POLYLINE' ;
THRESHOLD : 'THRESHOLD' | 'threshold' ;
TRANSLATE : 'TRANSLATE' | 'translate' ;
TRAJECTORY : 'TRAJECTORY' | 'trajectory' ;
TYPE : 'TYPE' | 'type' ;
UNCOMPARABLE : 'UNCOMPARABLE' | 'uncomparable' ;
UNKNOWN : 'UNKNOWN' | 'unknown' ;
UNNEST : 'UNNEST' | 'unnest' ;
UNPACK : 'UNPACK' | 'unpack' ;
USE : 'USE' | 'use' ;
USING : 'USING' | 'using' ;
VERSUS : 'DESC' | 'ASC' | 'desc' | 'asc' ;
WHERE : 'WHERE' | 'where' ;
WITH : 'WITH' | 'with' ;
WITHIN : 'WITHIN' | 'within' ;
WITHOUT : 'WITHOUT' | 'without' ;
WRT : 'WRT' | 'wrt' ;

// Punctuation
EQ : '=' ;
NEQ : '!=' ;
LE : '<=' ;
GE : '>=' ;
LT : '<' ;
GT : '>' ;
ADD : '+' ;
SUB : '-' ;
MUL : '*' ;
DIV : '/' ;
COMMA : ',' ;
COLON : ':' ;
SC : ';' ;
LP : '(' ;
RP : ')' ;
LB : '[' ;
RB : ']' ;
LBR : '{' ;
RBR : '}' ;
AT : 'AT' | '@' | 'at' ;

// Literals
FLOAT : [0-9]+ '.' [0-9]+ ;
INT : '0' | [1-9] [0-9]* ;
ID : [A-Za-z] [A-Za-z0-9_]* ;
FIELD_NAME : '.' [A-Za-z0-9~_]+ | '.' '"' ~["]* '"' ;
HASH_NAME : '#' [A-Za-z0-9~_]+ | '#' '"' ~["]* '"' ;
APEX_VALUE : '\'' ~[']* '\'' ;
QUOTED_VALUE : '"' ~["]* '"' ;

// Whitespace & Comments
WS : [ \t\r\n\u00A0]+ -> skip ;
LINE_COMMENT : '//' ~[\r\n]* -> skip ;
BLOCK_COMMENT : '/*' .*? '*/' -> skip ;

SCAN_ERROR : . ;