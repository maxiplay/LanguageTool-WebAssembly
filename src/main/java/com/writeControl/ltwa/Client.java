package com.writecontrol.ltwa;

import org.languagetool.JLanguageTool;
import org.languagetool.Language;
import org.languagetool.language.French;
import org.languagetool.rules.RuleMatch;

import java.io.IOException;
import java.util.List;

public class Client {
    public static void main(String[] args) throws IOException {

        Language language = new French();
        // List<Rule> rules = langTool.getAllRules();

         JLanguageTool langTool = new JLanguageTool(language);

       /* langTool.disableRule(HunspellRule.RULE_ID);
        langTool.disableRule(HunspellNoSuggestionRule.RULE_ID);*/

        List<RuleMatch> matchs = langTool.check("Les enfant aiment la soupe");

        System.out.println(matchs);

    }
}
