package com.simibubi.create.compat;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

/** Client-only compatibility correction for Create Adapted 1.31 with Iris 1.11.7.
 * Retains Iris' existing automatic mappings for two exact, verified pipelines.
 * No other reflective error or unknown mapping is ignored.
 */
final class IrisPipelineCompat$Mappings {
    static void register() {
        try {
            Class<?> apiClass = Class.forName("net.irisshaders.iris.api.v0.IrisApi");
            Object api = apiClass.getMethod("getInstance").invoke(null);
            Class<?> programs = Class.forName("net.irisshaders.iris.api.v0.IrisProgram");
            assign(apiClass, api, Class.forName("net.minecraft.client.renderer.RenderPipelines").getField("DEBUG_QUADS").get(null), programs.getField("BASIC").get(null));
            try {
                Object ghost = Class.forName("net.createmod.catnip.api.client.render.CatnipRenderPipelines").getField("GHOST_BLOCK").get(null);
                assign(apiClass, api, ghost, programs.getField("BLOCK_TRANSLUCENT").get(null));
            } catch (NoSuchFieldException ignored) {
                // Original adapter supports Catnip builds without the public ghost field.
            }
        } catch (ReflectiveOperationException failure) {
            throw new IllegalStateException("Cannot register Create/Iris pipelines", failure);
        }
    }
    private static void assign(Class<?> apiClass, Object api, Object pipeline, Object program) throws ReflectiveOperationException {
        for (Method method : apiClass.getMethods()) {
            if (!method.getName().equals("assignPipeline") || method.getParameterCount() != 2 || !method.getParameterTypes()[0].isInstance(pipeline) || !method.getParameterTypes()[1].isInstance(program)) continue;
            try {
                method.invoke(api, pipeline, program);
                return;
            } catch (InvocationTargetException wrapped) {
                Throwable cause = wrapped.getCause();
                String message = cause == null ? "" : cause.getMessage();
                if (cause instanceof IllegalStateException && (
                        "Shader already assigned: catnip:pipeline/ghost_block: TEXT_BE".equals(message) ||
                        "Shader already assigned: minecraft:pipeline/debug_quads: BASIC_COLOR".equals(message))) {
                    System.getLogger("mcj-create-iris").log(System.Logger.Level.INFO, "Retaining verified Iris mapping: " + message);
                    return;
                }
                throw wrapped;
            }
        }
        throw new NoSuchMethodException("Installed Iris has no compatible assignPipeline API");
    }
}
