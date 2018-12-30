package com.writecontrol.ltwa;

import org.languagetool.JLanguageTool;
import org.languagetool.Language;
import org.languagetool.language.French;
import org.languagetool.rules.RuleMatch;

import java.io.IOException;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.List;

public class Client {

    public static void main(String[] args) throws IOException {

        Language language = new French();
        // List<Rule> rules = langTool.getAllRules();

         JLanguageTool langTool = new JLanguageTool(language);

       /* langTool.disableRule(HunspellRule.RULE_ID);
        langTool.disableRule(HunspellNoSuggestionRule.RULE_ID);*/

       try{

           List<RuleMatch> matchs = langTool.check("Les enfant aiment la soupe");
           System.out.println(matchs);

       }catch(Exception e){

           System.out.println(e);

           System.out.println(e.getMessage());
           System.out.println(e.getCause());

           StringWriter errors = new StringWriter();
           e.printStackTrace(new PrintWriter(errors));

           System.out.println( errors.toString());

        }




    }
}
