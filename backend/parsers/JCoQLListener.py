# Generated from JCoQL.g4 by ANTLR 4.9.3
from antlr4 import *
if __name__ is not None and "." in __name__:
    from .JCoQLParser import JCoQLParser
else:
    from JCoQLParser import JCoQLParser

# This class defines a complete listener for a parse tree produced by JCoQLParser.
class JCoQLListener(ParseTreeListener):

    # Enter a parse tree produced by JCoQLParser#start.
    def enterStart(self, ctx:JCoQLParser.StartContext):
        pass

    # Exit a parse tree produced by JCoQLParser#start.
    def exitStart(self, ctx:JCoQLParser.StartContext):
        pass


    # Enter a parse tree produced by JCoQLParser#anyId.
    def enterAnyId(self, ctx:JCoQLParser.AnyIdContext):
        pass

    # Exit a parse tree produced by JCoQLParser#anyId.
    def exitAnyId(self, ctx:JCoQLParser.AnyIdContext):
        pass


    # Enter a parse tree produced by JCoQLParser#collectionReferenceRule.
    def enterCollectionReferenceRule(self, ctx:JCoQLParser.CollectionReferenceRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#collectionReferenceRule.
    def exitCollectionReferenceRule(self, ctx:JCoQLParser.CollectionReferenceRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#fieldRefRule.
    def enterFieldRefRule(self, ctx:JCoQLParser.FieldRefRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#fieldRefRule.
    def exitFieldRefRule(self, ctx:JCoQLParser.FieldRefRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#buildActionRule.
    def enterBuildActionRule(self, ctx:JCoQLParser.BuildActionRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#buildActionRule.
    def exitBuildActionRule(self, ctx:JCoQLParser.BuildActionRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#objectStructureRule.
    def enterObjectStructureRule(self, ctx:JCoQLParser.ObjectStructureRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#objectStructureRule.
    def exitObjectStructureRule(self, ctx:JCoQLParser.ObjectStructureRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#outputFieldSpecRule.
    def enterOutputFieldSpecRule(self, ctx:JCoQLParser.OutputFieldSpecRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#outputFieldSpecRule.
    def exitOutputFieldSpecRule(self, ctx:JCoQLParser.OutputFieldSpecRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#geometricOptionRule.
    def enterGeometricOptionRule(self, ctx:JCoQLParser.GeometricOptionRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#geometricOptionRule.
    def exitGeometricOptionRule(self, ctx:JCoQLParser.GeometricOptionRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#dropGeometryRule.
    def enterDropGeometryRule(self, ctx:JCoQLParser.DropGeometryRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#dropGeometryRule.
    def exitDropGeometryRule(self, ctx:JCoQLParser.DropGeometryRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#caseClauseRule.
    def enterCaseClauseRule(self, ctx:JCoQLParser.CaseClauseRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#caseClauseRule.
    def exitCaseClauseRule(self, ctx:JCoQLParser.CaseClauseRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#othersRule.
    def enterOthersRule(self, ctx:JCoQLParser.OthersRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#othersRule.
    def exitOthersRule(self, ctx:JCoQLParser.OthersRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#whereCaseRule.
    def enterWhereCaseRule(self, ctx:JCoQLParser.WhereCaseRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#whereCaseRule.
    def exitWhereCaseRule(self, ctx:JCoQLParser.WhereCaseRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#generateSectionRule.
    def enterGenerateSectionRule(self, ctx:JCoQLParser.GenerateSectionRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#generateSectionRule.
    def exitGenerateSectionRule(self, ctx:JCoQLParser.GenerateSectionRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#orConditionRule.
    def enterOrConditionRule(self, ctx:JCoQLParser.OrConditionRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#orConditionRule.
    def exitOrConditionRule(self, ctx:JCoQLParser.OrConditionRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#andConditionRule.
    def enterAndConditionRule(self, ctx:JCoQLParser.AndConditionRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#andConditionRule.
    def exitAndConditionRule(self, ctx:JCoQLParser.AndConditionRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#notConditionRule.
    def enterNotConditionRule(self, ctx:JCoQLParser.NotConditionRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#notConditionRule.
    def exitNotConditionRule(self, ctx:JCoQLParser.NotConditionRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#predicateRule.
    def enterPredicateRule(self, ctx:JCoQLParser.PredicateRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#predicateRule.
    def exitPredicateRule(self, ctx:JCoQLParser.PredicateRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#compareRule.
    def enterCompareRule(self, ctx:JCoQLParser.CompareRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#compareRule.
    def exitCompareRule(self, ctx:JCoQLParser.CompareRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#inRangeRule.
    def enterInRangeRule(self, ctx:JCoQLParser.InRangeRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#inRangeRule.
    def exitInRangeRule(self, ctx:JCoQLParser.InRangeRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#nullPredicateRule.
    def enterNullPredicateRule(self, ctx:JCoQLParser.NullPredicateRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#nullPredicateRule.
    def exitNullPredicateRule(self, ctx:JCoQLParser.NullPredicateRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#wukFuzzyPredicateRule.
    def enterWukFuzzyPredicateRule(self, ctx:JCoQLParser.WukFuzzyPredicateRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#wukFuzzyPredicateRule.
    def exitWukFuzzyPredicateRule(self, ctx:JCoQLParser.WukFuzzyPredicateRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#withoutPredicateRule.
    def enterWithoutPredicateRule(self, ctx:JCoQLParser.WithoutPredicateRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#withoutPredicateRule.
    def exitWithoutPredicateRule(self, ctx:JCoQLParser.WithoutPredicateRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#withPredicateRule.
    def enterWithPredicateRule(self, ctx:JCoQLParser.WithPredicateRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#withPredicateRule.
    def exitWithPredicateRule(self, ctx:JCoQLParser.WithPredicateRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#expressionRule.
    def enterExpressionRule(self, ctx:JCoQLParser.ExpressionRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#expressionRule.
    def exitExpressionRule(self, ctx:JCoQLParser.ExpressionRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#termRule.
    def enterTermRule(self, ctx:JCoQLParser.TermRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#termRule.
    def exitTermRule(self, ctx:JCoQLParser.TermRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#factorRule.
    def enterFactorRule(self, ctx:JCoQLParser.FactorRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#factorRule.
    def exitFactorRule(self, ctx:JCoQLParser.FactorRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#specialFunctionRule.
    def enterSpecialFunctionRule(self, ctx:JCoQLParser.SpecialFunctionRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#specialFunctionRule.
    def exitSpecialFunctionRule(self, ctx:JCoQLParser.SpecialFunctionRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#valueRule.
    def enterValueRule(self, ctx:JCoQLParser.ValueRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#valueRule.
    def exitValueRule(self, ctx:JCoQLParser.ValueRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#arrayFunctionRule.
    def enterArrayFunctionRule(self, ctx:JCoQLParser.ArrayFunctionRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#arrayFunctionRule.
    def exitArrayFunctionRule(self, ctx:JCoQLParser.ArrayFunctionRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#restrictedExpressionRule.
    def enterRestrictedExpressionRule(self, ctx:JCoQLParser.RestrictedExpressionRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#restrictedExpressionRule.
    def exitRestrictedExpressionRule(self, ctx:JCoQLParser.RestrictedExpressionRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#restrictedTermRule.
    def enterRestrictedTermRule(self, ctx:JCoQLParser.RestrictedTermRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#restrictedTermRule.
    def exitRestrictedTermRule(self, ctx:JCoQLParser.RestrictedTermRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#restrictedFactorRule.
    def enterRestrictedFactorRule(self, ctx:JCoQLParser.RestrictedFactorRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#restrictedFactorRule.
    def exitRestrictedFactorRule(self, ctx:JCoQLParser.RestrictedFactorRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#functionParamsRule.
    def enterFunctionParamsRule(self, ctx:JCoQLParser.FunctionParamsRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#functionParamsRule.
    def exitFunctionParamsRule(self, ctx:JCoQLParser.FunctionParamsRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#comparatorRule.
    def enterComparatorRule(self, ctx:JCoQLParser.ComparatorRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#comparatorRule.
    def exitComparatorRule(self, ctx:JCoQLParser.ComparatorRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#numericRule.
    def enterNumericRule(self, ctx:JCoQLParser.NumericRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#numericRule.
    def exitNumericRule(self, ctx:JCoQLParser.NumericRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#checkForFuzzySetRule.
    def enterCheckForFuzzySetRule(self, ctx:JCoQLParser.CheckForFuzzySetRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#checkForFuzzySetRule.
    def exitCheckForFuzzySetRule(self, ctx:JCoQLParser.CheckForFuzzySetRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#usingOrConditionRule.
    def enterUsingOrConditionRule(self, ctx:JCoQLParser.UsingOrConditionRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#usingOrConditionRule.
    def exitUsingOrConditionRule(self, ctx:JCoQLParser.UsingOrConditionRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#usingAndConditionRule.
    def enterUsingAndConditionRule(self, ctx:JCoQLParser.UsingAndConditionRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#usingAndConditionRule.
    def exitUsingAndConditionRule(self, ctx:JCoQLParser.UsingAndConditionRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#usingNotConditionRule.
    def enterUsingNotConditionRule(self, ctx:JCoQLParser.UsingNotConditionRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#usingNotConditionRule.
    def exitUsingNotConditionRule(self, ctx:JCoQLParser.UsingNotConditionRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#usingPredicateRule.
    def enterUsingPredicateRule(self, ctx:JCoQLParser.UsingPredicateRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#usingPredicateRule.
    def exitUsingPredicateRule(self, ctx:JCoQLParser.UsingPredicateRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#alphaCutRule.
    def enterAlphaCutRule(self, ctx:JCoQLParser.AlphaCutRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#alphaCutRule.
    def exitAlphaCutRule(self, ctx:JCoQLParser.AlphaCutRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#keepDropFuzzySetsRule.
    def enterKeepDropFuzzySetsRule(self, ctx:JCoQLParser.KeepDropFuzzySetsRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#keepDropFuzzySetsRule.
    def exitKeepDropFuzzySetsRule(self, ctx:JCoQLParser.KeepDropFuzzySetsRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#getCollectionRule.
    def enterGetCollectionRule(self, ctx:JCoQLParser.GetCollectionRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#getCollectionRule.
    def exitGetCollectionRule(self, ctx:JCoQLParser.GetCollectionRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#getDictionaryRule.
    def enterGetDictionaryRule(self, ctx:JCoQLParser.GetDictionaryRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#getDictionaryRule.
    def exitGetDictionaryRule(self, ctx:JCoQLParser.GetDictionaryRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#lookupFromWebRule.
    def enterLookupFromWebRule(self, ctx:JCoQLParser.LookupFromWebRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#lookupFromWebRule.
    def exitLookupFromWebRule(self, ctx:JCoQLParser.LookupFromWebRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#saveAsRule.
    def enterSaveAsRule(self, ctx:JCoQLParser.SaveAsRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#saveAsRule.
    def exitSaveAsRule(self, ctx:JCoQLParser.SaveAsRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#mergeCollectionsRule.
    def enterMergeCollectionsRule(self, ctx:JCoQLParser.MergeCollectionsRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#mergeCollectionsRule.
    def exitMergeCollectionsRule(self, ctx:JCoQLParser.MergeCollectionsRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#intersectCollectionsRule.
    def enterIntersectCollectionsRule(self, ctx:JCoQLParser.IntersectCollectionsRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#intersectCollectionsRule.
    def exitIntersectCollectionsRule(self, ctx:JCoQLParser.IntersectCollectionsRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#subtractCollectionsRule.
    def enterSubtractCollectionsRule(self, ctx:JCoQLParser.SubtractCollectionsRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#subtractCollectionsRule.
    def exitSubtractCollectionsRule(self, ctx:JCoQLParser.SubtractCollectionsRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#filterRule.
    def enterFilterRule(self, ctx:JCoQLParser.FilterRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#filterRule.
    def exitFilterRule(self, ctx:JCoQLParser.FilterRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#joinOfCollectionsRule.
    def enterJoinOfCollectionsRule(self, ctx:JCoQLParser.JoinOfCollectionsRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#joinOfCollectionsRule.
    def exitJoinOfCollectionsRule(self, ctx:JCoQLParser.JoinOfCollectionsRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#groupRule.
    def enterGroupRule(self, ctx:JCoQLParser.GroupRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#groupRule.
    def exitGroupRule(self, ctx:JCoQLParser.GroupRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#groupPartitionRule.
    def enterGroupPartitionRule(self, ctx:JCoQLParser.GroupPartitionRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#groupPartitionRule.
    def exitGroupPartitionRule(self, ctx:JCoQLParser.GroupPartitionRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#sortingFieldRule.
    def enterSortingFieldRule(self, ctx:JCoQLParser.SortingFieldRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#sortingFieldRule.
    def exitSortingFieldRule(self, ctx:JCoQLParser.SortingFieldRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#expandRule.
    def enterExpandRule(self, ctx:JCoQLParser.ExpandRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#expandRule.
    def exitExpandRule(self, ctx:JCoQLParser.ExpandRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#unpackRule.
    def enterUnpackRule(self, ctx:JCoQLParser.UnpackRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#unpackRule.
    def exitUnpackRule(self, ctx:JCoQLParser.UnpackRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#trajectoryMatchingRule.
    def enterTrajectoryMatchingRule(self, ctx:JCoQLParser.TrajectoryMatchingRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#trajectoryMatchingRule.
    def exitTrajectoryMatchingRule(self, ctx:JCoQLParser.TrajectoryMatchingRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#trajectoryPartitionRule.
    def enterTrajectoryPartitionRule(self, ctx:JCoQLParser.TrajectoryPartitionRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#trajectoryPartitionRule.
    def exitTrajectoryPartitionRule(self, ctx:JCoQLParser.TrajectoryPartitionRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#partitionMatchingRule.
    def enterPartitionMatchingRule(self, ctx:JCoQLParser.PartitionMatchingRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#partitionMatchingRule.
    def exitPartitionMatchingRule(self, ctx:JCoQLParser.PartitionMatchingRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#useDbRule.
    def enterUseDbRule(self, ctx:JCoQLParser.UseDbRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#useDbRule.
    def exitUseDbRule(self, ctx:JCoQLParser.UseDbRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#createJavaScriptFunctionRule.
    def enterCreateJavaScriptFunctionRule(self, ctx:JCoQLParser.CreateJavaScriptFunctionRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#createJavaScriptFunctionRule.
    def exitCreateJavaScriptFunctionRule(self, ctx:JCoQLParser.CreateJavaScriptFunctionRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#createJavaFunctionRule.
    def enterCreateJavaFunctionRule(self, ctx:JCoQLParser.CreateJavaFunctionRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#createJavaFunctionRule.
    def exitCreateJavaFunctionRule(self, ctx:JCoQLParser.CreateJavaFunctionRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#createEvaluatorRule.
    def enterCreateEvaluatorRule(self, ctx:JCoQLParser.CreateEvaluatorRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#createEvaluatorRule.
    def exitCreateEvaluatorRule(self, ctx:JCoQLParser.CreateEvaluatorRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#createFuzzyOperatorRule.
    def enterCreateFuzzyOperatorRule(self, ctx:JCoQLParser.CreateFuzzyOperatorRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#createFuzzyOperatorRule.
    def exitCreateFuzzyOperatorRule(self, ctx:JCoQLParser.CreateFuzzyOperatorRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#createFuzzyAggregatorRule.
    def enterCreateFuzzyAggregatorRule(self, ctx:JCoQLParser.CreateFuzzyAggregatorRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#createFuzzyAggregatorRule.
    def exitCreateFuzzyAggregatorRule(self, ctx:JCoQLParser.CreateFuzzyAggregatorRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#createFuzzyEvaluatorRule.
    def enterCreateFuzzyEvaluatorRule(self, ctx:JCoQLParser.CreateFuzzyEvaluatorRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#createFuzzyEvaluatorRule.
    def exitCreateFuzzyEvaluatorRule(self, ctx:JCoQLParser.CreateFuzzyEvaluatorRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#createFuzzySetModelRule.
    def enterCreateFuzzySetModelRule(self, ctx:JCoQLParser.CreateFuzzySetModelRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#createFuzzySetModelRule.
    def exitCreateFuzzySetModelRule(self, ctx:JCoQLParser.CreateFuzzySetModelRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#createGenericFuzzySetOperatorRule.
    def enterCreateGenericFuzzySetOperatorRule(self, ctx:JCoQLParser.CreateGenericFuzzySetOperatorRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#createGenericFuzzySetOperatorRule.
    def exitCreateGenericFuzzySetOperatorRule(self, ctx:JCoQLParser.CreateGenericFuzzySetOperatorRuleContext):
        pass


    # Enter a parse tree produced by JCoQLParser#createGenericFuzzyEvaluatorRule.
    def enterCreateGenericFuzzyEvaluatorRule(self, ctx:JCoQLParser.CreateGenericFuzzyEvaluatorRuleContext):
        pass

    # Exit a parse tree produced by JCoQLParser#createGenericFuzzyEvaluatorRule.
    def exitCreateGenericFuzzyEvaluatorRule(self, ctx:JCoQLParser.CreateGenericFuzzyEvaluatorRuleContext):
        pass



del JCoQLParser